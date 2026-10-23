"""Display-only STL parsing, bounds, hard edges and smooth shallow joins."""

import math
import struct
import unittest

from Partelier.partelier.tools.patterns.display_mesh import MAX_TRIANGLES, read_binary_stl


def binary_stl(facets):
    return bytes(80)+struct.pack('<I',len(facets))+b''.join(
        struct.pack('<12fH',0,0,0,*(coordinate for point in facet for coordinate in point),0)
        for facet in facets)


class DisplayMeshTests(unittest.TestCase):
    def test_coordinates_are_centimetres_and_hard_corner_normals_remain_separate(self):
        mesh=read_binary_stl(binary_stl([((0,0,0),(2,0,0),(0,3,0)),((0,0,0),(0,0,4),(2,0,0))]))
        self.assertEqual(mesh.triangle_count,2)
        self.assertEqual(max(mesh.coordinates),4)
        self.assertEqual(mesh.normals[:3],(0.,0.,1.))
        self.assertEqual(mesh.normals[9:12],(0.,1.,0.))

    def test_shallow_join_shares_smooth_normals_with_unit_length(self):
        angle=math.radians(15)
        mesh=read_binary_stl(binary_stl([((0,0,0),(1,0,0),(0,1,0)),
            ((1,0,0),(0,0,0),(0,-math.cos(angle),-math.sin(angle)))]))
        first=mesh.normals[:3];second=mesh.normals[12:15]
        for a,b in zip(first,second):self.assertAlmostEqual(a,b)
        self.assertGreater(abs(first[1]),.01)
        for index in range(0,len(mesh.normals),3):
            self.assertAlmostEqual(sum(x*x for x in mesh.normals[index:index+3]),1.)

    def test_invalid_truncated_over_budget_and_nonfinite_exports_are_refused(self):
        valid=binary_stl([((0,0,0),(1,0,0),(0,1,0))])
        bad=[b'',valid[:83],valid[:-1],valid+b'x',bytes(80)+struct.pack('<I',MAX_TRIANGLES+1),
            binary_stl([((math.nan,0,0),(1,0,0),(0,1,0))])]
        for value in bad:
            with self.subTest(length=len(value)),self.assertRaises(ValueError):read_binary_stl(value)

    def test_degenerate_facets_are_skipped_but_empty_result_is_refused(self):
        flat=((0,0,0),(0,0,0),(1,0,0))
        with self.assertRaisesRegex(ValueError,'no drawable'):read_binary_stl(binary_stl([flat]))
        good=((0,0,0),(1,0,0),(0,1,0))
        self.assertEqual(read_binary_stl(binary_stl([flat,good])).triangle_count,1)


if __name__=='__main__':unittest.main()
