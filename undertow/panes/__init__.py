"""Public pane and tree-view types for Undertow's workspace."""

from undertow.workspace import Pane

from .debug_controls import DebugControl, DebugControlsPane
from .editor import EditorPane
from .interpreter import InterpreterPane
from .inspector import InspectorPane
from .output import OutputPane
from .project import ProjectPane
from .terminal import TerminalPane
from .structure import StructurePane, StructureRow
from .variables import VariableRow, VariablesPane

__all__ = ["DebugControl", "DebugControlsPane", "EditorPane", "InspectorPane", "InterpreterPane", "OutputPane", "Pane", "ProjectPane", "StructurePane", "StructureRow", "TerminalPane", "VariableRow", "VariablesPane"]
