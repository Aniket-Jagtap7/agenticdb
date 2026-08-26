from typing import Any
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




def build_tool_decisions(
    action_requests: list,
    human_review: dict,
) -> list:
    """
    Convert the frontend review response into the decision
    structure expected by Command(resume={"decisions": ...}).
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

    decisions = []

    # APPROVE
    if decision_type == "approve":
        for action in action_requests:
            decisions.append(
                {
                    "type": "approve",
                    "action_name": action["name"],
                }
            )

        return decisions

    # RESPOND
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

    # REJECT
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

    # EDIT
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
        action_name = action["name"]

        original_args = dict(
            action.get("args", {})
        )

        # action_index is used because two actions might
        # have the same tool name.
        matching_edit = next(
            (
                edited_action
                for edited_action in edited_actions
                if (
                    edited_action.get(
                        "action_index"
                    )
                    == action_index
                )
            ),
            None,
        )

        changed_args = {}

        if matching_edit is not None:
            changed_args = matching_edit.get(
                "args",
                {},
            )

        if not isinstance(changed_args, dict):
            raise ValueError(
                f"Edited arguments for {action_name} "
                "must be an object."
            )

        # Begin with all original/default values.
        final_args = original_args.copy()

        for argument_name, new_value in (
            changed_args.items()
        ):
            # Empty means keep the existing value.
            if new_value is None:
                continue

            if (
                isinstance(new_value, str)
                and not new_value.strip()
            ):
                continue

            original_value = original_args.get(
                argument_name
            )

            final_args[argument_name] = (
                convert_edited_value(
                    new_value=new_value,
                    original_value=original_value,
                )
            )

        # Exactly one edit decision per tool action.
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

