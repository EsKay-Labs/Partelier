"""Local bounded JSONL diagnostics. Logging must never interrupt CAD work."""

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import uuid


MAX_BYTES = 2*1024*1024
BACKUPS = 3
_lock = threading.RLock()
_enabled = False
_run_id = None
_sequence = 0
_path = None


def log_path():
    return _path or Path(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir())/'Partelier/logs/partelier.jsonl'


def _safe(value, depth=0):
    if value is None or type(value) in (bool,int):return value
    if type(value) is float:return value if math.isfinite(value) else str(value)
    if isinstance(value,str):return value[:1024]
    if depth<3 and isinstance(value,dict):
        return {str(key)[:80]:_safe(item,depth+1) for key,item in list(value.items())[:40]}
    if depth<3 and isinstance(value,(tuple,list)):
        return [_safe(item,depth+1) for item in value[:40]]
    return type(value).__name__


def start(version, *, path=None):
    global _enabled,_run_id,_path,_sequence
    with _lock:
        _path=Path(path) if path is not None else None
        _run_id=str(uuid.uuid4());_sequence=0;_enabled=True
        emit('addin.start',version=version,pid=os.getpid(),loaded_diagnostics_build='0.34.0')


def emit(event, **fields):
    global _sequence
    if not _enabled:return False
    try:
        with _lock:
            _sequence+=1
            record={'utc':datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                    'monotonic_ms':round(time.perf_counter()*1000,3),'run_id':_run_id,
                    'sequence':_sequence,'thread':threading.current_thread().name,
                    'event':str(event)[:100],'data':_safe(fields)}
            line=json.dumps(record,ensure_ascii=True,allow_nan=False,separators=(',',':'))+'\n'
            path=log_path();path.parent.mkdir(parents=True,exist_ok=True)
            if path.exists() and path.stat().st_size+len(line.encode('utf-8'))>MAX_BYTES:
                for index in range(BACKUPS,0,-1):
                    source=path if index==1 else path.with_name(path.name+'.'+str(index-1))
                    target=path.with_name(path.name+'.'+str(index))
                    if source.exists():os.replace(source,target)
            with path.open('a',encoding='utf-8',newline='\n') as stream:stream.write(line)
        return True
    except Exception:
        return False


def _ui_value(value, depth=0):
    if value is None or type(value) in (bool,int):return value
    if type(value) is float and math.isfinite(value):return value
    if isinstance(value,str) and len(value)<=512:return value
    if depth<2 and isinstance(value,dict) and len(value)<=32:
        if not all(isinstance(key,str) and len(key)<=80 for key in value):
            raise ValueError('Invalid diagnostic context keys.')
        return {key:_ui_value(item,depth+1) for key,item in value.items()}
    raise ValueError('Use bounded diagnostic values.')


def validate_ui_entries(entries):
    if not isinstance(entries,list) or not 1<=len(entries)<=10:
        raise ValueError('Use one to ten diagnostic entries.')
    result=[]
    for entry in entries:
        if not isinstance(entry,dict) or set(entry)!={'event','at','context'}:
            raise ValueError('Invalid diagnostic entry.')
        name,at,context=entry['event'],entry['at'],entry['context']
        if not isinstance(name,str) or re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}',name) is None:
            raise ValueError('Invalid diagnostic event name.')
        try:finite=type(at) in (int,float) and math.isfinite(at) and at>=0
        except OverflowError:finite=False
        if not finite or not isinstance(context,dict):raise ValueError('Invalid diagnostic time or context.')
        result.append({'event':name,'at':at,'context':_ui_value(context)})
    return tuple(result)
