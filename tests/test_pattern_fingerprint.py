"""Bounded native-format point references and exact digest inputs."""

import hashlib
import json
from types import SimpleNamespace as N
import unittest
from unittest.mock import Mock,patch

from Partelier.partelier.tools.patterns import fingerprint as f
from Partelier.partelier.tools.hinge import fusion

HEADER=b'23200 0 2 2\n16 Autodesk Neutron 20 ASM example\n10 1e-6 1e-10\n'
FIXTURE=HEADER+b'body $-1 -1 $-1 $-1 $-1 $1 #\ntransform $-1 -1 1 0 0 0 1 0 0 0 1 0 0 0 1 no_rotate no_reflect no_shear #\nvertex $-1 -1 $-1 $-1 0 $3 #\npoint $-1 -1 $-1 1 2 3 #\nvertex $-1 -1 $-1 $-1 0 $3 #\nEnd-of-ASM-data\n'


class FingerprintTests(unittest.TestCase):
    def test_vertex_point_references_preserve_duplicate_coordinates(self):
        self.assertEqual(f.vertices(FIXTURE,2),((1.,2.,3.),(1.,2.,3.)))
        payload=b'body $-1 -1 $-1 $-1 $-1 $-1 #\n'
        text=b'fake # point $999'
        payload+=b'attribute @'+str(len(text)).encode()+b' '+text+b' #\n'
        payload+=b'vertex $-1 -1 $-1 $-1 0 $3 #\npoint $-1 -1 $-1 1 2 3 #\nEnd-of-ASM-data\n'
        self.assertEqual(f.vertices(HEADER+payload,1),((1.,2.,3.),))

    def test_unsupported_units_transforms_references_and_truncation_refuse(self):
        for data,count in ((FIXTURE,1),(FIXTURE.replace(b'10 1e-6',b'1 1e-6'),2),
                           (FIXTURE.replace(b'$3 #',b'$99 #'),2),
                           (FIXTURE.replace(b'1 0 0 0 1 0 0 0 1 0 0 0 1 no_rotate',b'1 0 0 0 1 0 0 0 1 2 0 0 1 no_rotate'),2),
                           (FIXTURE.replace(b'1 2 3 #',b'nan 2 3 #'),2),
                           (FIXTURE+b'body #',2),
                           (FIXTURE.replace(b'End-of-ASM-data',b''),2)):
            with self.subTest(data=data),self.assertRaises(ValueError):f.vertices(data,count)
        with self.assertRaises(ValueError):f.vertices(FIXTURE,2,bounds=((0,0,0),(1,1,1)))

    def test_size_record_and_vertex_budgets_are_checked(self):
        for limit in ('MAX_BYTES','MAX_RECORDS','MAX_VERTICES'):
            with patch.object(f,limit,1),self.assertRaises(ValueError):f.vertices(FIXTURE,2)

    def test_digest_matches_existing_sorted_rounded_geometry_contract(self):
        points=((1.123456789,2.,3.),(0.,0.,0.))
        data=(7,12,1,12.12345679,(0.,0.,0.),(5.,5.,5.),[(0.,0.,0.),(1.12345679,2.,3.)])
        expected=hashlib.sha256(json.dumps(data,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(f.digest(points,(7,12,1),12.123456789,((0.,0.,0.),(5.,5.,5.))),expected)

    def test_native_export_uses_only_smt_and_leaves_no_model_objects(self):
        def export(bodies,path):
            self.assertEqual(bodies,[body]);self.assertTrue(path.endswith('.smt'))
            from pathlib import Path
            Path(path).write_bytes(FIXTURE);return True
        manager=N(exportToFile=Mock(side_effect=export))
        body=N(vertices=N(count=2),faces=N(count=1),edges=N(count=2),lumps=N(count=1),volume=10,
               boundingBox=N(minPoint=N(x=0,y=0,z=0),maxPoint=N(x=5,y=5,z=5)))
        with patch.object(fusion,'_api',return_value=(None,N(TemporaryBRepManager=N(get=lambda:manager)))):
            value=f.signature(body)
        self.assertEqual(value,f.digest(((1.,2.,3.),)*2,(1,2,1),10,((0.,0.,0.),(5.,5.,5.))))

    def test_unsupported_bulk_export_falls_back_to_the_existing_exact_guard(self):
        from Partelier.partelier.tools.patterns import store
        for error in (ValueError('format'),RuntimeError('unavailable export'),OSError('file')):
            with patch.object(f,'signature',side_effect=error),patch.object(store,'_signature',return_value='legacy-digest') as legacy:
                body=object()
                self.assertEqual(store._cut_signature(body),'legacy-digest')
                legacy.assert_called_once_with(body)
