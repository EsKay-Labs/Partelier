"""Exact grille vertex digest through Fusion's bounded native SMT export.

Only the observed ASM format with centimetre coordinates and identity body
transforms is accepted. Unsupported exports fall back to the existing SDK
vertex walk in the caller. No SAT export or model/history entities are used.
"""

import hashlib
import json
import math
from pathlib import Path
import re
import tempfile

MAX_BYTES=64*1024*1024
MAX_RECORDS=400000
MAX_VERTICES=100000
IDENTITY=(1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.)


def _numbers(values):
    try:return tuple(float(value) for value in values)
    except (TypeError,OverflowError) as error:raise ValueError('Invalid SMT numeric fields.') from error


def _tokens(data):
    index=0;size=len(data)
    while index<size:
        if data[index] in b' \t\r\n':index+=1;continue
        if data[index]==35:
            yield b'#';index+=1;continue
        if data[index]==64:
            start=index+1;end=start
            while end<size and 48<=data[end]<=57:end+=1
            if end==start or end>=size or data[end] not in b' \t\r\n':raise ValueError('Invalid SMT string length.')
            length=int(data[start:end]);index=end+1+length
            if index>size:raise ValueError('Truncated SMT string.')
            yield None
            continue
        end=index
        while end<size and data[end] not in b' \t\r\n#':end+=1
        yield data[index:end];index=end


def vertices(data,expected_count,*,bounds=None):
    """Read each vertex's point reference, retaining coordinate multiplicity."""
    if not isinstance(data,bytes) or len(data)>MAX_BYTES or not 1<=expected_count<=MAX_VERTICES:
        raise ValueError('SMT fingerprint exceeds its work budget.')
    try:version,producer,units,payload=data.split(b'\n',3)
    except ValueError as error:raise ValueError('Missing SMT header.') from error
    if not re.fullmatch(rb'\d+\s+\d+\s+\d+\s+\d+\s*',version):raise ValueError('Unsupported SMT header.')
    if not 22000<=int(version.split()[0])<=30000:raise ValueError('Unsupported ASM version.')
    values=_numbers(units.split())
    if len(values)!=3 or values[0]!=10 or not all(math.isfinite(x) for x in values):raise ValueError('Unsupported SMT units.')
    records=[];record=[];finished=False
    stream=iter(_tokens(payload));sentinel=object()
    for token in stream:
        if token==b'End-of-ASM-data':
            if record:raise ValueError('Incomplete SMT record.')
            if next(stream,sentinel) is not sentinel:raise ValueError('Unexpected data after the SMT body.')
            finished=True;break
        if token!=b'#':record.append(token);continue
        if not record:raise ValueError('Empty SMT record.')
        if record[0] is not None and re.fullmatch(rb'-\d+',record[0]):
            if abs(int(record.pop(0)))!=len(records):raise ValueError('Invalid SMT record index.')
        records.append(tuple(record));record=[]
        if len(records)>MAX_RECORDS:raise ValueError('Too many SMT records.')
    if not finished or sum(value[0]==b'body' for value in records)!=1:raise ValueError('Expected one complete SMT body.')
    for value in records:
        if value[0]==b'transform':
            if len(value)<16 or _numbers(value[3:16])!=IDENTITY:raise ValueError('Unsupported SMT body transform.')
    points=[]
    for value in records:
        if value[0]!=b'vertex':continue
        references=[]
        for token in value[1:]:
            if token is None or not re.fullmatch(rb'\$\d+',token):continue
            index=int(token[1:])
            if index>=len(records):raise ValueError('Invalid SMT vertex reference.')
            if records[index][0]==b'point':references.append(records[index])
        if len(references)!=1 or len(references[0])!=7:raise ValueError('Unsupported SMT vertex point.')
        point=_numbers(references[0][-3:])
        if not all(math.isfinite(x) for x in point):raise ValueError('Non-finite SMT point.')
        if bounds is not None and any(x<lo-1e-6 or x>hi+1e-6 for x,lo,hi in zip(point,*bounds)):
            raise ValueError('SMT point is outside the original body bounds.')
        points.append(point)
        if len(points)>expected_count:raise ValueError('SMT vertex count mismatch.')
    if len(points)!=expected_count:raise ValueError('SMT vertex count mismatch.')
    return tuple(points)


def digest(points,counts,volume,bounds):
    rounded=sorted(tuple(round(value,8) for value in point) for point in points)
    data=(*counts,round(float(volume),8),*(tuple(round(value,8) for value in point) for point in bounds),rounded)
    return hashlib.sha256(json.dumps(data,separators=(',',':')).encode('utf-8')).hexdigest()


def signature(body):
    from ..hinge.fusion import _api,_xyz
    _,native=_api();manager=native.TemporaryBRepManager.get()
    bounds=(_xyz(body.boundingBox.minPoint),_xyz(body.boundingBox.maxPoint))
    count=body.vertices.count
    if not 1<=count<=MAX_VERTICES:raise ValueError('Too many fingerprint vertices.')
    with tempfile.TemporaryDirectory(prefix='partelier-fingerprint-') as folder:
        path=Path(folder)/'body.smt'
        if manager.exportToFile([body],str(path)) is False:raise ValueError('Fusion could not export the fingerprint geometry.')
        if not path.is_file() or path.stat().st_size>MAX_BYTES:raise ValueError('Fingerprint export exceeds its work budget.')
        points=vertices(path.read_bytes(),count,bounds=bounds)
    return digest(points,(body.faces.count,body.edges.count,body.lumps.count),body.volume,bounds)
