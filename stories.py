from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UserSession:
    user_id: int
    root_controller: "Controller"


@dataclass
class Event:
    user_id: int


@dataclass
class ButtonAction(Event):
    name: str


@dataclass
class Message(Event):
    text: str


@dataclass
class Command(Event):
    name: str
    args: list[str]


@dataclass
class Button:
    text: str
    action: str

    def __init__(self, text: str, action: Optional[str] = None):
        self.text = text
        self.action = action if action else text.lower()

    def __post_init__(self):
        if self.action is None:
            self.action = self.text.lower()


@dataclass
class OutMessage:
    text: str
    buttons: list[list[Button]] = field(default_factory=list)
    next: Optional["OutMessage"] = None
    parse_mode: Optional[str] = None
    buttons_below: Optional[list[list[Button]]] = None
    edit_the_last: bool = (
        False  # Indicates that the message should be sent as an edit to the last one
    )

    def __add__(self, other: "OutMessage") -> "OutMessage":
        insert_after = self
        while insert_after.next:
            insert_after = insert_after.next
        insert_after.next = other
        return self

    def __repr__(self) -> str:
        next = "..." if self.next else None
        s_edit = " EDIT" if self.edit_the_last else ""
        return f"OutMessage(text={repr(self.text[:30])}, next={next}, parse_mode={self.parse_mode}, buttons={repr(self.buttons)}, buttons_below={repr(self.buttons_below)}{s_edit})"


@dataclass
class Controller:
    parent: Optional["Controller"] = None
    child: Optional["Controller"] = None
    text: Optional[str] = ""
    buttons: list[list[Button]] = field(default_factory=list)
    buttons_below: Optional[list[list[Button]]] = None
    parse_mode: Optional[str] = None

    def process_event(self, e: Event) -> OutMessage:
        return self.render()

    def render(self) -> OutMessage:
        if self.child:
            return self.child.render()
        else:
            return OutMessage(
                self.text if self.text else "",
                self.buttons,
                parse_mode=self.parse_mode,
                buttons_below=self.buttons_below,
            )

    def show_child(self, child: "Controller") -> OutMessage:
        child.parent = self
        self.child = child
        return child.render()

    def close(self) -> OutMessage:
        if self.parent is None:
            raise ValueError("Can't close root controller")
        self.parent.child = None
        return self.parent.on_child_closed(self)

    def on_child_closed(self, child: "Controller") -> OutMessage:
        return self.render()

    def get_current_active(self) -> "Controller":
        if self.child:
            return self.child.get_current_active()
        return self

    def get_button_by_action(self, action: str) -> Optional[Button]:
        for line in self.buttons:
            for button in line:
                if button.action == action:
                    return button
        return None


@dataclass
class YesNoController(Controller):
    result: Optional[bool] = None

    def __init__(self, parent: Controller, question: str):
        Controller.__init__(
            self,
            parent=parent,
            text=question,
            buttons=[[Button("Yes", "yes"), Button("No", "no")]],
        )

    def process_event(self, e: Event) -> OutMessage:
        if isinstance(e, ButtonAction):
            if e.name in ("yes", "no"):
                self.result = e.name == "yes"
                return self.close()
        raise ValueError("Unexpected event")
