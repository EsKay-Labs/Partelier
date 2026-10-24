"""Fixed read-only inspection of the loaded product's pattern preview lifecycle."""

import json
from pathlib import Path
import sys


def inspect(app):
    expected = Path(__file__).resolve().parents[3] / 'Partelier/partelier/addin.py'
    owners = []
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        try:
            if Path(filename).resolve() != expected:
                continue
        except (OSError, ValueError):
            continue
        owner = getattr(module, '_pattern_commands', None)
        if owner is None:
            continue
        runner = owner.runner
        session = owner._session
        request = runner._current
        command = runner._command
        owners.append({
            'session': owner.palette_state(),
            'owner_busy': owner._busy,
            'pending_commit': owner._pending is not None,
            'runner_busy': runner.busy,
            'runner_stopped': runner._stopped,
            'runner_pending': runner._pending is not None,
            'command_valid': command.isValid if command is not None else None,
            'command_id': runner._command_id,
            'event_registered': runner._custom_event is not None,
            'event_id': runner._event_id,
            'request': None if request is None else {
                'serial': request.serial, 'computed': request.computed,
                'executed': request.executed, 'cancelled': request.cancelled,
                'has_result': request.prepared is not None,
                'error': str(request.error) if request.error is not None else None,
            },
            'has_preview': session.preview is not None if session is not None else False,
            'prepared_timings': getattr(getattr(session, 'prepared', None), 'timings', None),
            'prepared_cell_count': getattr(getattr(session, 'prepared', None), 'cell_count', None),
        })
    ui=app.userInterface
    selections=[ui.activeSelections.item(i).entity.objectType for i in range(min(100,ui.activeSelections.count))]
    select_definitions=[{'id':ui.commandDefinitions.item(i).id,'name':ui.commandDefinitions.item(i).name}
        for i in range(ui.commandDefinitions.count) if 'select' in ui.commandDefinitions.item(i).id.lower()][:40]
    return {'scenario': 'pattern_status', 'success': True, 'read_only': True,
            'native_selection_types':selections,'select_definitions':select_definitions,
            'fusion_version': app.version, 'active_command': app.userInterface.activeCommand,
            'owners': owners}


def run(context):
    import adsk.core
    context = context if isinstance(context, dict) else {}
    report = inspect(adsk.core.Application.get())
    path = context.get('report_path')
    if path:
        Path(path).write_text(json.dumps(report, indent=2), encoding='utf-8')
    callback = context.get('on_complete')
    if callback is not None:
        callback(report)
