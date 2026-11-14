"""
Every call inside the SDK that writes an order record says what is left of the position after it.

quantity_left is what check_open_orders reads to say a position is open or closed, and convert_to_trades ends a trade on an exit
that leaves nothing open. The writers (place_vt_order, place_bt_order, place_bt_leg_order, save_lt_order) default quantity_left to 0,
so a call that forgets it would record a partial exit as the last one. Today every call passes it; this keeps it so. A call that
spreads **kwargs is not checked: it cannot be read.

Offline: reads source files only.
"""
import ast
import pathlib

import trigerr

RECORD_WRITERS = {"place_vt_order", "place_bt_order", "place_bt_leg_order", "save_lt_order"}


def calls_without_quantity_left():
    package = pathlib.Path(trigerr.__file__).parent
    found = []
    for path in package.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None
            keywords = {keyword.arg for keyword in node.keywords}
            if name in RECORD_WRITERS and "quantity_left" not in keywords and None not in keywords:
                found.append(f"{path.relative_to(package)}:{node.lineno} {name}")
    return found


def test_every_call_that_writes_an_order_record_passes_quantity_left():
    assert calls_without_quantity_left() == []
