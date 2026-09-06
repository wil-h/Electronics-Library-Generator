import adsk.core
import traceback
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_THIS_DIR, 'lib')
for p in (_THIS_DIR, _LIB_DIR):
    if p not in sys.path:
        sys.path.append(p)

from AWSServer import MouserClient

# Global variables to keep handlers/objects alive
_app = None
_ui = None
_handlers = []

CMD_ID = 'libraryAddin_cmdBtn'
CMD_NAME = 'Generate Electronics Library'
CMD_DESCRIPTION = 'Creates an electronics library from an excel file with mouser numbers'
PANEL_ID = 'SolidScriptsAddinsPanel'  
WORKSPACE_ID = 'FusionSolidEnvironment'
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources')
SESSION_FILE = os.path.join(_THIS_DIR, 'session.json')

def execute():
    if not os.path.exists(SESSION_FILE):
        result = _ui.messageBox(
            'This add-in needs permission to view your autodesk account to prevent abuse of the mouser api. This information is not stored\n\n'
            'Click OK to open in browser.',
            'Permissions Required',
            adsk.core.MessageBoxButtonTypes.OKCancelButtonType,
            adsk.core.MessageBoxIconTypes.QuestionIconType
        )
        if result != adsk.core.DialogResults.DialogOK:
            return  # user cancelled, don't proceed to login

    mouser = MouserClient()
    mouser.login()
    partnum = mouser.search_part("595-TLV1701AIDCKRG4")
    _ui.messageBox(partnum, "Success:")
#---------------------------fusion integration setup--------------------------------
class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            execute()
        except:
            if _ui:
                _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            cmd = args.command
            on_execute = CommandExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)
        except:
            if _ui:
                _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        cmd_defs = _ui.commandDefinitions
        cmd_def = cmd_defs.itemById(CMD_ID)
        if not cmd_def:
            cmd_def = cmd_defs.addButtonDefinition(
                CMD_ID,
                CMD_NAME,
                CMD_DESCRIPTION,
                ICON_FOLDER
            )

        on_created = CommandCreatedHandler()
        cmd_def.commandCreated.add(on_created)
        _handlers.append(on_created)

        workspace = _ui.workspaces.itemById(WORKSPACE_ID)
        panel = workspace.toolbarPanels.itemById(PANEL_ID)
        control = panel.controls.itemById(CMD_ID)
        if not control:
            control = panel.controls.addCommand(cmd_def)
            control.isPromoted = True
            control.isPromotedByDefault = True

    except:
        if _ui:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


def stop(context):
    try:
        workspace = _ui.workspaces.itemById(WORKSPACE_ID)
        panel = workspace.toolbarPanels.itemById(PANEL_ID)
        control = panel.controls.itemById(CMD_ID)
        if control:
            control.deleteMe()

        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()
    except:
        if _ui:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))