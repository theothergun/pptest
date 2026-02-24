from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Barfi Studio", layout="wide")

st.title("Barfi Studio")
st.caption("Visual flow builder for generating StepChain script stubs.")

try:
    from barfi import Block, st_barfi
except Exception as exc:
    st.error("Barfi is not installed in this Python environment.")
    st.code("pip install barfi streamlit")
    st.exception(exc)
    st.stop()


def _mk_constant_block() -> Block:
    blk = Block(name="Constant")
    blk.add_option(name="Value", type="input")
    blk.add_output(name="out")

    def compute(self: Block) -> None:
        value = self.get_option(name="Value")
        self.set_interface(name="out", value=value)

    blk.add_compute(compute)
    return blk


def _mk_notify_block() -> Block:
    blk = Block(name="UI Notify")
    blk.add_input(name="message")
    blk.add_option(name="Type", type="select", items=["info", "positive", "warning", "negative"])
    blk.add_output(name="command")

    def compute(self: Block) -> None:
        message = self.get_interface(name="message")
        n_type = self.get_option(name="Type") or "info"
        self.set_interface(
            name="command",
            value={"action": "notify", "message": str(message or ""), "type": n_type},
        )

    blk.add_compute(compute)
    return blk


st.subheader("Canvas")
result = st_barfi(base_blocks=[_mk_constant_block(), _mk_notify_block()], compute_engine=True)

st.subheader("Result")
st.write(result)

script_name = st.text_input("Export script name", value="barfi_generated")
if st.button("Export StepChain script stub"):
    out_dir = Path(os.environ.get("BARFI_EXPORT_DIR", "scripts/barfi_generated"))
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{script_name.strip() or 'barfi_generated'}.py"

    template = f'''"""Generated from Barfi Studio."""

def run(ctx):
    # result snapshot from Barfi compute engine
    graph_result = {result!r}

    # Example: send message to NiceGUI app
    commands = graph_result if isinstance(graph_result, list) else [graph_result]
    for item in commands:
        if isinstance(item, dict) and item.get("action") == "notify":
            ctx.ui.notify(item.get("message", ""), item.get("type", "info"))

    # keep chain alive
    ctx.wait(0.1, next_step=0, desc="Barfi-driven loop")
'''
    target.write_text(template, encoding="utf-8")
    st.success(f"Script exported to {target}")
