from algosdk.transaction import OnComplete
from pyteal import TxnField, TxnType, Int, Expr
from pyteal.ast import abi


def delete_txn_fields(app_id: abi.Uint64) -> dict[TxnField, Expr | list[Expr]]:
    return {
        TxnField.type_enum: TxnType.ApplicationCall,
        TxnField.application_id: app_id.get(),
        TxnField.on_completion: Int(OnComplete.DeleteApplicationOC.value),
    }
