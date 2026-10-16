from typing import Any
from copy import deepcopy
import json


def convert_edited_value(
    new_value: Any,
    original_value: Any,
) -> Any:
    """
    Convert an edited frontend value to the type of the
    original tool argument.

    Browser input values normally arrive as strings.
    """

    if not isinstance(new_value, str):
        return new_value

    stripped_value = new_value.strip()

    if isinstance(original_value, bool):
        normalized = stripped_value.lower()

        if normalized in {
            "true",
            "yes",
            "1",
        }:
            return True

        if normalized in {
            "false",
            "no",
            "0",
        }:
            return False

        raise ValueError(
            f"Invalid boolean value: {new_value}"
        )

    # bool is also an int in Python, so boolean handling
    # must appear before integer handling.
    if isinstance(original_value, int):
        return int(stripped_value)

    if isinstance(original_value, float):
        return float(stripped_value)

    if isinstance(original_value, list):
        converted_value = json.loads(
            stripped_value
        )

        if not isinstance(converted_value, list):
            raise ValueError(
                "The edited value must be a JSON list."
            )

        return converted_value

    if isinstance(original_value, dict):
        converted_value = json.loads(
            stripped_value
        )

        if not isinstance(converted_value, dict):
            raise ValueError(
                "The edited value must be a JSON object."
            )

        return converted_value

    if original_value is None:
        # Try to parse JSON values such as numbers,
        # booleans, lists, dictionaries, and null.
        try:
            return json.loads(stripped_value)
        except json.JSONDecodeError:
            return stripped_value

    return stripped_value




from copy import deepcopy
from typing import Any


def merge_edited_arguments(
    original: dict[str, Any],
    edited: dict[str, Any],
) -> dict[str, Any]:
    """
    Recursively merge edited arguments into original arguments.

    Empty strings and None retain the original value.
    Existing argument types are preserved where possible.
    """

    merged = deepcopy(original)

    for key, new_value in edited.items():
        if new_value is None:
            continue

        if (
            isinstance(new_value, str)
            and not new_value.strip()
        ):
            continue

        original_value = original.get(key)

        if (
            isinstance(original_value, dict)
            and isinstance(new_value, dict)
        ):
            merged[key] = merge_edited_arguments(
                original=original_value,
                edited=new_value,
            )
        else:
            merged[key] = convert_edited_value(
                new_value=new_value,
                original_value=original_value,
            )

    return merged


def build_tool_decisions(
    action_requests: list[dict[str, Any]],
    human_review: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Convert the frontend HITL response into the decision
    structure required by Command(resume={"decisions": ...}).

    Supported decisions:
    - approve
    - edit
    - respond
    - reject
    """

    if not isinstance(human_review, dict):
        raise ValueError(
            "The human review response must be an object."
        )

    decision_type = str(
        human_review.get("decision", "")
    ).strip().lower()

    allowed_decisions = {
        "approve",
        "edit",
        "respond",
        "reject",
    }

    if decision_type not in allowed_decisions:
        raise ValueError(
            "Decision must be approve, edit, respond, "
            "or reject."
        )

    decisions: list[dict[str, Any]] = []

    # -----------------------------------------------------
    # APPROVE
    # -----------------------------------------------------

    if decision_type == "approve":
        for action in action_requests:
            decisions.append(
                {
                    "type": "approve",
                    "action_name": action["name"],
                }
            )

        return decisions

    # -----------------------------------------------------
    # RESPOND
    # -----------------------------------------------------

    if decision_type == "respond":
        response_message = str(
            human_review.get("message", "")
        ).strip()

        if not response_message:
            raise ValueError(
                "A response message is required."
            )

        for action in action_requests:
            decisions.append(
                {
                    "type": "respond",
                    "action_name": action["name"],
                    "message": (
                        "HUMAN REVIEW RESPONSE: "
                        f"{response_message}"
                    ),
                }
            )

        return decisions

    # -----------------------------------------------------
    # REJECT
    # -----------------------------------------------------

    if decision_type == "reject":
        rejection_reason = str(
            human_review.get("message", "")
        ).strip()

        if not rejection_reason:
            raise ValueError(
                "A rejection reason is required."
            )

        for action in action_requests:
            decisions.append(
                {
                    "type": "reject",
                    "action_name": action["name"],
                    "message": (
                        "HUMAN REVIEW REJECTED: "
                        f"{rejection_reason}"
                    ),
                }
            )

        return decisions

    # -----------------------------------------------------
    # EDIT
    # -----------------------------------------------------

    edited_actions = human_review.get(
        "edited_actions",
        [],
    )

    if not isinstance(edited_actions, list):
        raise ValueError(
            "edited_actions must be a list."
        )

    for action_index, action in enumerate(
        action_requests
    ):
        if not isinstance(action, dict):
            raise ValueError(
                "Each action request must be an object."
            )

        action_name = action.get("name")

        if not action_name:
            raise ValueError(
                "Each action request must have a name."
            )

        original_args = action.get(
            "args",
            {},
        )

        if not isinstance(original_args, dict):
            raise ValueError(
                f"Original arguments for {action_name} "
                "must be an object."
            )

        matching_edit = None

        # First try action_index because it uniquely identifies
        # actions when the same tool is requested multiple times.
        for edited_action in edited_actions:
            if not isinstance(edited_action, dict):
                continue

            edited_action_index = edited_action.get(
                "action_index"
            )

            if edited_action_index == action_index:
                matching_edit = edited_action
                break

        # The current React frontend sends action_name.
        if matching_edit is None:
            for edited_action in edited_actions:
                if not isinstance(edited_action, dict):
                    continue

                if (
                    edited_action.get("action_name")
                    == action_name
                ):
                    matching_edit = edited_action
                    break

        if matching_edit is None:
            # No changes supplied for this action.
            edited_args = {}
        else:
            edited_args = matching_edit.get(
                "args",
                {},
            )

        if not isinstance(edited_args, dict):
            raise ValueError(
                f"Edited arguments for {action_name} "
                "must be an object."
            )

        final_args = merge_edited_arguments(
            original=original_args,
            edited=edited_args,
        )

        decisions.append(
            {
                "type": "edit",
                "action_name": action_name,
                "edited_action": {
                    "name": action_name,
                    "args": final_args,
                },
            }
        )

    return decisions