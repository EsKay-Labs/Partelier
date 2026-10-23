"""Batching matches the exact sequential geometry and never mutates fallback inputs."""

import math
from types import SimpleNamespace
import unittest

from Partelier.partelier.tools.patterns.batch import try_through_difference


class Body:
    def __init__(self, voxels, *, temporary=True):
        self.voxels=set(voxels)
        self.isTemporary=temporary
        self.isValid=True
        self.solid=True
        self.volume_error=0.0
        self.depth=0

    @property
    def isSolid(self):return self.solid and bool(self.voxels)

    @property
    def volume(self):return len(self.voxels)*.01+self.volume_error

    @property
    def lumps(self):
        remaining=set(self.voxels)
        count=0
        while remaining:
            count+=1
            pending=[remaining.pop()]
            while pending:
                x,y,z=pending.pop()
                for neighbor in ((x-1,y,z),(x+1,y,z),(x,y-1,z),(x,y+1,z),(x,y,z-1),(x,y,z+1)):
                    if neighbor in remaining:
                        remaining.remove(neighbor);pending.append(neighbor)
        return SimpleNamespace(count=count)


TYPES=SimpleNamespace(UnionBooleanType='union',DifferenceBooleanType='difference')


class Manager:
    def __init__(self, *, fail_union=None, fail_difference=False, raises=False,
                 corrupt_union=False, corrupt_difference=False, alias_copy=False, copy_failure=False):
        self.fail_union=fail_union
        self.fail_difference=fail_difference
        self.raises=raises
        self.corrupt_union=corrupt_union
        self.corrupt_difference=corrupt_difference
        self.alias_copy=alias_copy
        self.copy_failure=copy_failure
        self.calls=[]
        self.copies=[]
        self.max_depth=0

    def copy(self,body):
        if self.copy_failure:raise RuntimeError('injected copy failure')
        if self.alias_copy:return body
        result=Body(body.voxels)
        result.volume_error=body.volume_error
        self.copies.append((body,result))
        return result

    def booleanOperation(self,target,tool,operation):
        if not target.isTemporary:raise AssertionError('A persistent source became a Boolean target')
        self.calls.append(operation)
        if operation=='union':
            target.voxels|=tool.voxels
            target.depth=max(target.depth,tool.depth)+1
            self.max_depth=max(self.max_depth,target.depth)
            failing=self.fail_union==self.calls.count('union')
            if self.corrupt_union:target.volume_error=.01
        elif operation=='difference':
            target.voxels-=tool.voxels
            failing=self.fail_difference
            if self.corrupt_difference:target.volume_error=.01
        else:raise AssertionError('Unexpected Boolean operation')
        if failing:
            # Model the difficult kernel case: its target changed BEFORE False
            # or an exception. The original inputs must still be untouched.
            target.voxels.clear()
            if self.raises:raise RuntimeError('injected partially-mutating native failure')
            return False
        return True


def fixtures(count=8):
    width=count*2+3
    source=Body(((x,y,z) for x in range(width) for y in range(5) for z in range(2)),temporary=False)
    tools=tuple(Body(((2+2*index,2,z) for z in range(2))) for index in range(count))
    return source,tools


def signatures(source,tools):return tuple(frozenset(body.voxels) for body in (source,*tools))


def sequential(source,tools):
    manager=Manager()
    result=manager.copy(source)
    for tool in tools:
        before=result.volume
        if not manager.booleanOperation(result,tool,'difference') or result.lumps.count!=1:
            raise ValueError('Original sequential single-solid guard')
        if before-result.volume<=1e-10:raise ValueError('Original per-cell contribution guard')
    return result


class PatternBatchTests(unittest.TestCase):
    def test_batch_matches_exact_sequential_holes_for_even_and_odd_counts(self):
        for count in (8,9,17):
            with self.subTest(count=count):
                source,tools=fixtures(count)
                before=signatures(source,tools)
                expected=sequential(source,tools)
                manager=Manager()
                batch=try_through_difference(manager,source,tools,TYPES)
                self.assertIsNotNone(batch)
                self.assertEqual(batch.body.voxels,expected.voxels)
                self.assertTrue(batch.body.isTemporary)
                self.assertEqual(batch.body.lumps.count,1)
                self.assertEqual(batch.tool_count,count)
                self.assertEqual(signatures(source,tools),before)
                for tool in tools:self.assertTrue(source.voxels>=tool.voxels and not batch.body.voxels&tool.voxels)
                self.assertTrue({(0,2,0),(1,2,0),(2,1,0),(2,3,0)}<=batch.body.voxels,'border/web material remains')

    def test_balanced_tree_and_single_final_difference_have_bounded_native_calls(self):
        source,tools=fixtures(17)
        manager=Manager()
        batch=try_through_difference(manager,source,tools,TYPES)
        self.assertEqual(manager.calls.count('union'),len(tools)-1)
        self.assertEqual(manager.calls.count('difference'),1)
        self.assertLessEqual(manager.max_depth,math.ceil(math.log2(len(tools))))
        self.assertEqual(len(manager.copies),len(tools)+1)
        self.assertEqual(batch.timings['batch_union_calls'],16)
        self.assertGreaterEqual(batch.timings['batch_total_ms'],0)
        self.assertAlmostEqual(batch.timings['batch_total_ms'],batch.timings['batch_aggregate_ms']+batch.timings['batch_apply_ms'])
        self.assertTrue(all(copy is not original for original,copy in manager.copies))

    def test_small_patterns_use_original_path_without_native_copies_or_booleans(self):
        for count in (0,1,7):
            with self.subTest(count=count):
                source,tools=fixtures(count)
                manager=Manager()
                self.assertIsNone(try_through_difference(manager,source,tools,TYPES))
                self.assertEqual(manager.calls,[])
                self.assertEqual(manager.copies,[])

    def test_overlapping_or_touching_tools_refuse_batch_without_skipping_material_guards(self):
        for touching in (False,True):
            source,tools=fixtures(8)
            if touching:tools=(*tools[:1],Body(((3,2,z) for z in range(2))),*tools[2:])
            else:tools=(*tools[:1],Body(tools[0].voxels),*tools[2:])
            before=signatures(source,tools)
            self.assertIsNone(try_through_difference(Manager(),source,tools,TYPES))
            self.assertEqual(signatures(source,tools),before)
            if not touching:
                with self.assertRaisesRegex(ValueError,'per-cell contribution'):sequential(source,tools)

    def test_partially_mutating_union_failures_leave_exact_inputs_for_fresh_fallback(self):
        for raises in (False,True):
            for failing_union in (1,4,7):
                with self.subTest(raises=raises,failing_union=failing_union):
                    source,tools=fixtures()
                    before=signatures(source,tools)
                    expected=sequential(source,tools).voxels
                    manager=Manager(fail_union=failing_union,raises=raises)
                    self.assertIsNone(try_through_difference(manager,source,tools,TYPES))
                    self.assertEqual(signatures(source,tools),before)
                    self.assertEqual(sequential(source,tools).voxels,expected)
                    self.assertNotIn('difference',manager.calls)

    def test_partially_mutating_final_difference_failure_never_leaks_as_fallback_source(self):
        for raises in (False,True):
            with self.subTest(raises=raises):
                source,tools=fixtures()
                before=signatures(source,tools)
                expected=sequential(source,tools).voxels
                manager=Manager(fail_difference=True,raises=raises)
                self.assertIsNone(try_through_difference(manager,source,tools,TYPES))
                self.assertEqual(signatures(source,tools),before)
                self.assertEqual(sequential(source,tools).voxels,expected)

    def test_split_final_source_refuses_batch_and_keeps_sequential_single_solid_error(self):
        source,tools=fixtures()
        tools=tuple(Body(((2+2*index,y,z) for y in range(5) for z in range(2))) for index in range(8))
        before=signatures(source,tools)
        self.assertIsNone(try_through_difference(Manager(),source,tools,TYPES))
        self.assertEqual(signatures(source,tools),before)
        with self.assertRaisesRegex(ValueError,'single-solid'):sequential(source,tools)

    def test_aggregate_or_final_volume_mismatch_refuses_unsafe_batch(self):
        for manager in (Manager(corrupt_union=True),Manager(corrupt_difference=True)):
            source,tools=fixtures()
            before=signatures(source,tools)
            self.assertIsNone(try_through_difference(manager,source,tools,TYPES))
            self.assertEqual(signatures(source,tools),before)

    def test_cutters_outside_original_source_do_not_pass_expected_volume_check(self):
        source,tools=fixtures()
        tools=(*tools[:-1],Body(((100,2,z) for z in range(2))))
        before=signatures(source,tools)
        self.assertIsNone(try_through_difference(Manager(),source,tools,TYPES))
        self.assertEqual(signatures(source,tools),before)

    def test_copy_alias_or_failure_refuses_before_any_boolean_targets_input_geometry(self):
        for manager in (Manager(alias_copy=True),Manager(copy_failure=True)):
            source,tools=fixtures()
            before=signatures(source,tools)
            self.assertIsNone(try_through_difference(manager,source,tools,TYPES))
            self.assertEqual(manager.calls,[])
            self.assertEqual(signatures(source,tools),before)

    def test_tiny_contribution_uses_old_per_cell_delta_path(self):
        source,tools=fixtures()
        tools[0].volume_error=-.02+1e-11
        manager=Manager()
        self.assertGreater(tools[0].volume,0)
        self.assertIsNone(try_through_difference(manager,source,tools,TYPES))
        self.assertEqual(manager.calls,[])
        self.assertEqual(manager.copies,[])

    def test_invalid_initial_solids_and_non_temporary_cutters_raise(self):
        for attribute,value in (('isValid',False),('solid',False),('volume_error',float('nan'))):
            source,tools=fixtures()
            setattr(tools[0],attribute,value)
            with self.subTest(attribute=attribute),self.assertRaises(ValueError):
                try_through_difference(Manager(),source,tools,TYPES)
        source,tools=fixtures()
        tools[0].isTemporary=False
        with self.assertRaises(ValueError):try_through_difference(Manager(),source,tools,TYPES)
        with self.assertRaises(ValueError):try_through_difference(Manager(),None,tools,TYPES)
        source,tools=fixtures()
        tools[0].voxels|={(100,0,0)}
        with self.assertRaises(ValueError):try_through_difference(Manager(),source,tools,TYPES)
        with self.assertRaises(ValueError):try_through_difference(Manager(),source,None,TYPES)

    def test_invalid_thresholds_are_refused(self):
        source,tools=fixtures()
        for threshold in (0,1,401,True,1.5):
            with self.subTest(threshold=threshold),self.assertRaises(ValueError):
                try_through_difference(Manager(),source,tools,TYPES,min_tools=threshold)

    def test_cutter_that_consumes_entire_source_is_left_for_original_refusal(self):
        source,tools=fixtures()
        tools=tuple(Body(((x,y,z) for x in range(i*2,(i+1)*2) for y in range(5) for z in range(2)))
                    for i in range(8))
        source.voxels=set().union(*(tool.voxels for tool in tools))
        manager=Manager()
        self.assertIsNone(try_through_difference(manager,source,tools,TYPES))
        self.assertEqual(manager.calls,[])


if __name__=='__main__':unittest.main()
