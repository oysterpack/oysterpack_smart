import base64

import algosdk
from algosdk.transaction import (
    OnComplete,
    StateSchema,
    ApplicationCreateTxn,
    ApplicationUpdateTxn,
    ApplicationDeleteTxn,
    ApplicationOptInTxn,
    ApplicationCloseOutTxn,
    ApplicationClearStateTxn,
    ApplicationNoOpTxn,
)

from oysterpack.algorand.model import Address, AppID, AssetID, BoxKey
from oysterpack.algorand.transactions import GetSuggestedParams, create_lease


def base64_encode_arg(arg: bytes | bytearray | str | int) -> bytes:
    """
    Encodes an argument for an application call
    """
    return base64.b64encode(algosdk.encoding.encode_as_bytes(arg))


def base64_decode_int_arg(arg: str | bytes) -> int:
    """
    Decodes an int arg that was encoded for an application call.
    """
    return int.from_bytes(base64.b64decode(arg), byteorder="big")


def base64_decode_str_arg(arg: str | bytes) -> str:
    """
    Decodes a str arg that was encoded for an application call.
    """
    return base64.b64decode(arg).decode()


def create_smart_contract(
    *,
    sender: Address,
    suggested_params: GetSuggestedParams,
    approval_program: bytes,
    clear_program: bytes,
    global_schema: StateSchema,
    local_schema: StateSchema,
    app_args: list[bytes] | None = None,
    accounts: list[Address] | None = None,
    foreign_apps: list[AppID] | None = None,
    foreign_assets: list[AssetID] | None = None,
    note: bytes | None = None,
    extra_pages: int = 0,
    boxes: list[tuple[AppID, BoxKey]] | None = None,
) -> ApplicationCreateTxn:
    return ApplicationCreateTxn(
        sender=sender,
        sp=suggested_params(),
        lease=create_lease(),
        on_complete=OnComplete.NoOpOC,
        approval_program=approval_program,
        clear_program=clear_program,
        global_schema=global_schema,
        local_schema=local_schema,
        app_args=app_args,
        accounts=accounts,
        foreign_apps=foreign_apps,
        foreign_assets=foreign_assets,
        extra_pages=extra_pages,
        note=note,
        boxes=boxes,
    )


def update_smart_contract(
    *,
    sender: Address,
    suggested_params: GetSuggestedParams,
    app_id: AppID,
    approval_program: bytes,
    clear_program: bytes,
    app_args: list[bytes] | None = None,
    note: bytes | None = None,
    boxes: list[tuple[AppID, BoxKey]] | None = None,
) -> ApplicationUpdateTxn:
    return ApplicationUpdateTxn(
        sender=sender,
        index=app_id,
        sp=suggested_params(),
        lease=create_lease(),
        approval_program=approval_program,
        clear_program=clear_program,
        app_args=app_args,
        note=note,
        boxes=boxes,
    )


def delete_smart_contract(
    *,
    sender: Address,
    suggested_params: GetSuggestedParams,
    app_id: AppID,
    note: bytes | None = None,
) -> ApplicationDeleteTxn:
    return ApplicationDeleteTxn(
        sender=sender,
        index=app_id,
        sp=suggested_params(),
        lease=create_lease(),
        note=note,
    )


def optin_smart_contract(
    *,
    sender: Address,
    suggested_params: GetSuggestedParams,
    app_id: AppID,
    note: bytes | None = None,
) -> ApplicationOptInTxn:
    """
    An Application Opt-In transaction must be submitted by an account in order for the local state for that account to
    be used. If no local state is required, this transaction is not necessary for a given account.
    """

    return ApplicationOptInTxn(
        sender=sender,
        index=app_id,
        sp=suggested_params(),
        lease=create_lease(),
        note=note,
    )


def close_out_smart_contract(
    *,
    sender: Address,
    suggested_params: GetSuggestedParams,
    app_id: AppID,
    note: bytes | None = None,
) -> ApplicationCloseOutTxn:
    """
    An Application Close Out transaction is used when an account wants to opt out of a contract gracefully and remove
    its local state from its balance record. This transaction may fail according to the logic in the Approval program.
    """

    return ApplicationCloseOutTxn(
        sender=sender,
        index=app_id,
        sp=suggested_params(),
        lease=create_lease(),
        note=note,
    )


def force_close_out_smart_contract(
    *,
    sender: Address,
    suggested_params: GetSuggestedParams,
    app_id: AppID,
    note: bytes | None = None,
) -> ApplicationClearStateTxn:
    """
    An Application Clear State transaction is used to force removal of the local state from the balance record of the
    sender. Given a well-formed transaction this method will always succeed. The Clear program is used by the application
    to perform any bookkeeping necessary to remove the Account from its records.
    """

    return ApplicationClearStateTxn(
        sender=sender,
        index=app_id,
        sp=suggested_params(),
        lease=create_lease(),
        note=note,
    )


def call(
    *,
    sender: Address,
    suggested_params: GetSuggestedParams,
    app_id: AppID,
    app_args: list[bytes] | None = None,
    accounts: list[Address] | None = None,
    foreign_apps: list[AppID] | None = None,
    foreign_assets: list[AssetID] | None = None,
    note: bytes | None = None,
    boxes: list[tuple[AppID, BoxKey]] | None = None,
) -> ApplicationNoOpTxn:
    return ApplicationNoOpTxn(
        sender=sender,
        sp=suggested_params(),
        lease=create_lease(),
        index=app_id,
        app_args=app_args,
        accounts=accounts,
        foreign_apps=foreign_apps,
        foreign_assets=foreign_assets,
        note=note,
        boxes=boxes,
    )
