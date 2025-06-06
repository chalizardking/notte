import inspect
import json
import operator
import re
from abc import ABCMeta, abstractmethod
from functools import reduce
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator
from typing_extensions import override

from notte_core.browser.dom_tree import NodeSelectors
from notte_core.credentials.types import ValueWithPlaceholder
from notte_core.errors.actions import InvalidActionError

# ############################################################
# Action enums
# ############################################################

ActionStatus = Literal["valid", "failed", "excluded"]
AllActionStatus = ActionStatus | Literal["all"]
ActionRole = Literal["link", "button", "input", "special", "image", "option", "misc", "other"]
AllActionRole = ActionRole | Literal["all"]

EXCLUDED_ACTIONS = {"fallback_observe"}

typeAlias = type


class ActionParameter(BaseModel):
    name: str
    type: str
    default: str | None = None
    values: list[str] = Field(default_factory=list)

    def description(self) -> str:
        base = f"{self.name}: {self.type}"
        if len(self.values) > 0:
            base += f" = [{', '.join(self.values)}]"
        return base


class ActionParameterValue(BaseModel):
    name: str
    value: str | ValueWithPlaceholder


# ############################################################
# Browser actions models
# ############################################################


class BaseAction(BaseModel, metaclass=ABCMeta):
    """Base model for all actions."""

    type: str
    category: Annotated[str, Field(exclude=True, description="Category of the action", min_length=1)]
    description: Annotated[str, Field(exclude=True, description="Description of the action", min_length=1)]

    @property
    def id(self) -> str:
        data = self.model_dump()
        if "id" in data:
            return data["id"]
        return self.type

    @field_validator("type", mode="after")
    @classmethod
    def verify_type_equals_name(cls, value: Any) -> Any:
        """Validator necessary to ignore typing issues with ValueWithPlaceholder"""
        # assert type == cls.name()

        if value != cls.name():
            raise ValueError(f"Type {value} does not match {cls.name()}")
        return value

    ACTION_REGISTRY: ClassVar[dict[str, typeAlias["BaseAction"]]] = {}

    @staticmethod
    def validate_type(action_type: str) -> bool:
        return action_type in BaseAction.ACTION_REGISTRY

    def __init_subclass__(cls, **kwargs: dict[Any, Any]):
        super().__init_subclass__(**kwargs)  # type: ignore

        if not inspect.isabstract(cls):
            name = cls.name()
            if name in EXCLUDED_ACTIONS:
                return
            if name in {"browser", "interaction", "step", "action", "fallback_observe"}:
                return
            if name in cls.ACTION_REGISTRY:
                raise ValueError(f"Base Action {name} is duplicated")
            cls.ACTION_REGISTRY[name] = cls

    @classmethod
    def non_agent_fields(cls) -> set[str]:
        fields = {
            # Base action fields
            "id",
            "category",
            "description",
            # Interaction action fields
            "selector",
            "press_enter",
            "option_selector",
            "text_label",
            # executable action fields
            "params",
            "code",
            "status",
            "locator",
        }
        if "selector" in cls.model_fields or "locator" in cls.model_fields:
            fields.remove("id")
        return fields

    @classmethod
    def name(cls) -> str:
        """Convert a CamelCase string to snake_case"""
        pattern = re.compile(r"(?<!^)(?=[A-Z])")
        return pattern.sub("_", cls.__name__).lower().replace("_action", "")

    @abstractmethod
    def execution_message(self) -> str:
        """Return the message to be displayed when the action is executed."""
        return f"🚀 Successfully executed action: {self.description}"

    def model_dump_agent(self) -> dict[str, dict[str, Any]]:
        return self.model_dump(exclude=self.non_agent_fields())

    def model_dump_agent_json(self) -> str:
        return json.dumps(self.model_dump(exclude=self.non_agent_fields()))


class BrowserAction(BaseAction, metaclass=ABCMeta):
    """Base model for special actions that are always available and not related to the current page."""

    category: str = "Special Browser Actions"

    BROWSER_ACTION_REGISTRY: ClassVar[dict[str, typeAlias["BrowserAction"]]] = {}

    def __init_subclass__(cls, **kwargs: dict[Any, Any]):
        super().__init_subclass__(**kwargs)

        if not inspect.isabstract(cls):
            name = cls.name()
            if name in cls.BROWSER_ACTION_REGISTRY:
                raise ValueError(f"Base Action {name} is duplicated")
            cls.BROWSER_ACTION_REGISTRY[name] = cls

    @staticmethod
    def is_browser_action(action_type: str) -> bool:
        return action_type in BrowserAction.BROWSER_ACTION_REGISTRY

    @staticmethod
    @abstractmethod
    def example() -> "BrowserAction":
        raise NotImplementedError("This method should be implemented by the subclass")

    @staticmethod
    def list() -> list["BrowserAction"]:
        return [action.example() for action in BrowserAction.BROWSER_ACTION_REGISTRY.values()]

    @property
    @abstractmethod
    def param(self) -> ActionParameter | None:
        raise NotImplementedError("This method should be implemented by the subclass")

    @staticmethod
    def from_param(action_type: str, value: str | int | None = None) -> "BrowserAction":
        if action_type not in BrowserAction.BROWSER_ACTION_REGISTRY:
            raise ValueError(f"Invalid action type: {action_type}")
        action_cls = BrowserAction.BROWSER_ACTION_REGISTRY[action_type]
        param = action_cls.example().param
        action_params = {}
        if param is not None and value is not None:
            action_params[param.name] = value
        return action_cls.model_validate(action_params)


class GotoAction(BrowserAction):
    type: Literal["goto"] = "goto"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Goto to a URL (in current tab)"
    url: str

    # Allow 'id' to be a field name
    model_config = {"extra": "forbid", "protected_namespaces": ()}  # type: ignore[reportUnknownMemberType]

    __pydantic_fields_set__ = {"url"}  # type: ignore[reportUnknownMemberType]

    @override
    def execution_message(self) -> str:
        return f"Navigated to '{self.url}' in current tab"

    @override
    @staticmethod
    def example() -> "GotoAction":
        return GotoAction(url="<some_url>")

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="url", type="str")


class GotoNewTabAction(BrowserAction):
    type: Literal["goto_new_tab"] = "goto_new_tab"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Goto to a URL (in new tab)"
    url: str

    @override
    def execution_message(self) -> str:
        return f"Navigated to '{self.url}' in new tab"

    @override
    @staticmethod
    def example() -> "GotoNewTabAction":
        return GotoNewTabAction(url="<some_url>")

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="url", type="str")


class SwitchTabAction(BrowserAction):
    type: Literal["switch_tab"] = "switch_tab"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Switch to a tab (identified by its index)"
    tab_index: int

    @override
    def execution_message(self) -> str:
        return f"Switched to tab {self.tab_index}"

    @override
    @staticmethod
    def example() -> "SwitchTabAction":
        return SwitchTabAction(tab_index=0)

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="tab_index", type="int")


class ScrapeAction(BrowserAction):
    type: Literal["scrape"] = "scrape"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = (
        "Scrape the current page data in text format. "
        "If `instructions` is null then the whole page will be scraped. "
        "Otherwise, only the data that matches the instructions will be scraped. "
        "Instructions should be given as natural language, e.g. 'Extract the title and the price of the product'"
    )
    instructions: str | None = None
    only_main_content: Annotated[
        bool,
        Field(
            description="Whether to only scrape the main content of the page. If True, navbars, footers, etc. are excluded."
        ),
    ] = True

    @override
    def execution_message(self) -> str:
        return "Scraped the current page data in text format"

    @override
    @staticmethod
    def example() -> "ScrapeAction":
        return ScrapeAction(instructions="<some_instructions>")

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="instructions", type="str")


class GoBackAction(BrowserAction):
    type: Literal["go_back"] = "go_back"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Go back to the previous page (in current tab)"

    @override
    def execution_message(self) -> str:
        return "Navigated back to the previous page"

    @override
    @staticmethod
    def example() -> "GoBackAction":
        return GoBackAction()

    @property
    @override
    def param(self) -> ActionParameter | None:
        return None


class GoForwardAction(BrowserAction):
    type: Literal["go_forward"] = "go_forward"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Go forward to the next page (in current tab)"

    @override
    def execution_message(self) -> str:
        return "Navigated forward to the next page"

    @override
    @staticmethod
    def example() -> "GoForwardAction":
        return GoForwardAction()

    @property
    @override
    def param(self) -> ActionParameter | None:
        return None


class ReloadAction(BrowserAction):
    type: Literal["reload"] = "reload"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Reload the current page"

    @override
    def execution_message(self) -> str:
        return "Reloaded the current page"

    @override
    @staticmethod
    def example() -> "ReloadAction":
        return ReloadAction()

    @property
    @override
    def param(self) -> ActionParameter | None:
        return None


class WaitAction(BrowserAction):
    type: Literal["wait"] = "wait"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Wait for a given amount of time (in milliseconds)"
    time_ms: int

    @override
    def execution_message(self) -> str:
        return f"Waited for {self.time_ms} milliseconds"

    @override
    @staticmethod
    def example() -> "WaitAction":
        return WaitAction(time_ms=1000)

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="time_ms", type="int")


class PressKeyAction(BrowserAction):
    type: Literal["press_key"] = "press_key"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Press a keyboard key: e.g. 'Enter', 'Backspace', 'Insert', 'Delete', etc."
    key: str

    @override
    def execution_message(self) -> str:
        return f"Pressed the keyboard key: {self.key}"

    @override
    @staticmethod
    def example() -> "PressKeyAction":
        return PressKeyAction(key="<some_key>")

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="key", type="str")


class ScrollUpAction(BrowserAction):
    type: Literal["scroll_up"] = "scroll_up"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Scroll up by a given amount of pixels. Use `null` for scrolling up one page"
    # amount of pixels to scroll. None for scrolling up one page
    amount: int | None = None

    @override
    def execution_message(self) -> str:
        return f"Scrolled up by {str(self.amount) + ' pixels' if self.amount is not None else 'one page'}"

    @override
    @staticmethod
    def example() -> "ScrollUpAction":
        return ScrollUpAction(amount=None)

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="amount", type="int")


class ScrollDownAction(BrowserAction):
    type: Literal["scroll_down"] = "scroll_down"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Scroll down by a given amount of pixels. Use `null` for scrolling down one page"
    # amount of pixels to scroll. None for scrolling down one page
    amount: int | None = None

    @override
    def execution_message(self) -> str:
        return f"Scrolled down by {str(self.amount) + ' pixels' if self.amount is not None else 'one page'}"

    @override
    @staticmethod
    def example() -> "ScrollDownAction":
        return ScrollDownAction(amount=None)

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="amount", type="int")


# ############################################################
# Special action models
# ############################################################


class HelpAction(BrowserAction):
    type: Literal["help"] = "help"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Ask for clarification"
    reason: str

    @override
    def execution_message(self) -> str:
        return f"Required help for task: {self.reason}"

    @override
    @staticmethod
    def example() -> "HelpAction":
        return HelpAction(reason="<some_reason>")

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="reason", type="str")


class CompletionAction(BrowserAction):
    type: Literal["completion"] = "completion"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Complete the task by returning the answer and terminate the browser session"
    success: bool
    answer: str

    @override
    def execution_message(self) -> str:
        return f"Completed the task with success: {self.success} and answer: {self.answer}"

    @override
    @staticmethod
    def example() -> "CompletionAction":
        return CompletionAction(success=True, answer="<some_answer>")

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="answer", type="str")


# ############################################################
# Interaction actions models
# ############################################################


class InteractionAction(BaseAction, metaclass=ABCMeta):
    id: str  # pyright: ignore [reportIncompatibleMethodOverride]
    selector: NodeSelectors | None = Field(default=None, exclude=True)
    category: str = Field(default="Interaction Actions", min_length=1)
    press_enter: bool | None = Field(default=None, exclude=True)
    text_label: str | None = Field(default=None, exclude=True)
    param: ActionParameter | None = Field(default=None, exclude=True)

    INTERACTION_ACTION_REGISTRY: ClassVar[dict[str, typeAlias["InteractionAction"]]] = {}

    def __init_subclass__(cls, **kwargs: dict[Any, Any]):
        super().__init_subclass__(**kwargs)

        if not inspect.isabstract(cls):
            name = cls.name()
            if name in cls.INTERACTION_ACTION_REGISTRY:
                raise ValueError(f"Base Action {name} is duplicated")
            cls.INTERACTION_ACTION_REGISTRY[name] = cls


class ClickAction(InteractionAction):
    type: Literal["click"] = "click"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Click on an element of the current page"

    @override
    def execution_message(self) -> str:
        return f"Clicked on the element with text label: {self.text_label}"


class FallbackObserveAction(BaseAction):
    type: Literal["fallback_observe"] = "fallback_observe"  # pyright: ignore [reportIncompatibleVariableOverride]
    category: str = "Special Browser Actions"
    description: str = "Can't be picked: perform observation"

    @override
    def execution_message(self) -> str:
        return "Performed fallback observation"


class FillAction(InteractionAction):
    type: Literal["fill"] = "fill"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Fill an input field with a value"
    value: str | ValueWithPlaceholder
    clear_before_fill: bool = True
    param: ActionParameter | None = Field(default=ActionParameter(name="value", type="str"), exclude=True)

    @field_validator("value", mode="before")
    @classmethod
    def verify_value(cls, value: Any) -> Any:
        """Validator necessary to ignore typing issues with ValueWithPlaceholder"""
        return value

    @override
    def execution_message(self) -> str:
        return f"Filled the input field '{self.text_label}' with the value: '{self.value}'"


class MultiFactorFillAction(InteractionAction):
    type: Literal["multi_factor_fill"] = "multi_factor_fill"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Fill an MFA input field with a value. CRITICAL: Only use it when filling in an OTP."
    value: str | ValueWithPlaceholder
    clear_before_fill: bool = True
    param: ActionParameter | None = Field(default=ActionParameter(name="value", type="str"), exclude=True)

    @field_validator("value", mode="before")
    @classmethod
    def verify_value(cls, value: Any) -> Any:
        """Validator necessary to ignore typing issues with ValueWithPlaceholder"""
        return value

    @override
    def execution_message(self) -> str:
        return f"Filled the MFA input field with the value: '{self.value}'"


class FallbackFillAction(InteractionAction):
    type: Literal["fallback_fill"] = "fallback_fill"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Fill an input field with a value. Only use if explicitly asked, or you failed to input with the normal fill action"
    value: str | ValueWithPlaceholder
    clear_before_fill: bool = True
    param: ActionParameter | None = Field(default=ActionParameter(name="value", type="str"), exclude=True)

    @field_validator("value", mode="before")
    @classmethod
    def verify_value(cls, value: Any) -> Any:
        """Validator necessary to ignore typing issues with ValueWithPlaceholder"""
        return value

    @override
    def execution_message(self) -> str:
        return f"Filled (fallback) the input field '{self.text_label}' with the value: '{self.value}'"


class CheckAction(InteractionAction):
    type: Literal["check"] = "check"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Check a checkbox. Use `True` to check, `False` to uncheck"
    value: bool
    param: ActionParameter | None = Field(default=ActionParameter(name="value", type="bool"), exclude=True)

    @override
    def execution_message(self) -> str:
        return f"Checked the checkbox '{self.text_label}'" if self.text_label is not None else "Checked the checkbox"


# class ListDropdownOptionsAction(InteractionAction):
#     id: str
#     description: str = "List all options of a dropdown"
#
#     @override
#     def execution_message(self) -> str:
#         return (
#             f"Listed all options of the dropdown '{self.text_label}'"
#             if self.text_label is not None
#             else "Listed all options of the dropdown"
#         )


class SelectDropdownOptionAction(InteractionAction):
    type: Literal["select_dropdown_option"] = "select_dropdown_option"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = (
        "Select an option from a dropdown. The `id` field should be set to the select element's id. "
        "Then you can either set the `value` field to the option's text or the `option_id` field to the option's `id`."
    )
    value: str | ValueWithPlaceholder
    param: ActionParameter | None = Field(default=ActionParameter(name="value", type="str"), exclude=True)

    @field_validator("value", mode="before")
    @classmethod
    def verify_value(cls, value: Any) -> Any:
        """Validator necessary to ignore typing issues with ValueWithPlaceholder"""
        return value

    @override
    def execution_message(self) -> str:
        return (
            f"Selected the option '{self.value}' from the dropdown '{self.text_label}'"
            if self.text_label is not None and self.text_label != ""
            else f"Selected the option '{self.value}' from the dropdown '{self.id}'"
        )


BrowserActionUnion = Annotated[
    reduce(operator.or_, BrowserAction.BROWSER_ACTION_REGISTRY.values()), Field(discriminator="type")
]
InteractionActionUnion = Annotated[
    reduce(operator.or_, InteractionAction.INTERACTION_ACTION_REGISTRY.values()), Field(discriminator="type")
]
ActionUnion = Annotated[reduce(operator.or_, BaseAction.ACTION_REGISTRY.values()), Field(discriminator="type")]


class ActionValidation(BaseModel):
    action: ActionUnion


class StepAction(InteractionAction):
    """
    An action that can be executed by the proxy.
    """

    # description is not needed for the proxy
    type: Literal["step"] = "step"  # pyright: ignore [reportIncompatibleVariableOverride]
    category: str = "Step Actions"
    description: str = "Step action"
    value: ActionParameterValue | None = None

    @override
    def execution_message(self) -> str:
        return f"Executed action with description: {self.description} and text: {self.text_label}"

    @property
    def role(self, raise_error: bool = False) -> ActionRole:
        if not self.id:
            if raise_error:
                raise InvalidActionError(self.id, "Action ID cannot be empty")
            return "other"
        match self.id[0]:
            case "L":
                return "link"
            case "B":
                return "button"
            case "I":
                return "input"
            case "O":
                return "option"
            case "M":
                return "misc"
            case "F":
                # figure / image
                return "image"
            case _:
                if raise_error:
                    raise InvalidActionError(
                        self.id, f"First ID character must be one of {ActionRole} but got {self.id[0]}"
                    )
                return "other"
