from __future__ import annotations

from nicegui import ui

from layout.context import PageContext


_BLOCKLY_HTML = r'''
<div class="w-full" style="height: 78vh; min-height: 560px; border: 1px solid #ddd; border-radius: 10px; overflow: hidden;">
  <div id="blockly-toolbar" style="display:flex; gap:8px; padding:10px; border-bottom:1px solid #eee; align-items:center; flex-wrap:wrap;">
    <button id="btn-save" style="padding:6px 10px; border:1px solid #bbb; border-radius:8px; background:#fff; cursor:pointer;">Save Workspace</button>
    <button id="btn-load" style="padding:6px 10px; border:1px solid #bbb; border-radius:8px; background:#fff; cursor:pointer;">Load Workspace</button>
    <button id="btn-clear" style="padding:6px 10px; border:1px solid #bbb; border-radius:8px; background:#fff; cursor:pointer;">Clear</button>
    <button id="btn-export" style="padding:6px 10px; border:1px solid #bbb; border-radius:8px; background:#fff; cursor:pointer;">Export Python</button>
    <span style="font-size:12px; color:#666;">Workspace key: <code>mes.blockly.workspace.v1</code></span>
  </div>
  <div id="blocklyDiv" style="height: calc(100% - 50px); width:100%;"></div>
</div>

<xml id="toolbox" style="display:none">
  <category name="Logic" categorystyle="logic_category"></category>
  <category name="Loops" categorystyle="loop_category"></category>
  <category name="Math" categorystyle="math_category"></category>
  <category name="Text" categorystyle="text_category"></category>
  <category name="Lists" categorystyle="list_category"></category>
  <category name="Colour" categorystyle="colour_category"></category>
  <category name="Variables" categorystyle="variable_category"></category>
  <category name="Functions" categorystyle="procedure_category"></category>
</xml>

<script src="https://unpkg.com/blockly/blockly.min.js"></script>
<script src="https://unpkg.com/blockly/python_compressed"></script>
<script>
(function() {
  if (!window.Blockly) {
    console.error('Blockly failed to load.');
    return;
  }

  const STORAGE_KEY = 'mes.blockly.workspace.v1';
  const host = document.getElementById('blocklyDiv');
  if (!host || host.dataset.blocklyReady === '1') return;

  host.dataset.blocklyReady = '1';
  const workspace = Blockly.inject(host, {
    toolbox: document.getElementById('toolbox'),
    grid: {spacing: 20, length: 3, colour: '#ddd', snap: true},
    move: {scrollbars: true, drag: true, wheel: true},
    trashcan: true,
    zoom: {controls: true, wheel: true, startScale: 1.0, maxScale: 2, minScale: 0.3, scaleSpeed: 1.2},
    theme: Blockly.Themes.Zelos,
  });

  const save = () => {
    const state = Blockly.serialization.workspaces.save(workspace);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  };

  const load = () => {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    try {
      Blockly.Events.disable();
      workspace.clear();
      Blockly.serialization.workspaces.load(JSON.parse(raw), workspace);
      return true;
    } catch (e) {
      console.error('Failed to load workspace', e);
      return false;
    } finally {
      Blockly.Events.enable();
    }
  };

  if (!load()) {
    const xmlText = '<xml xmlns="https://developers.google.com/blockly/xml"><block type="controls_if" x="30" y="30"></block></xml>';
    const xml = Blockly.utils.xml.textToDom(xmlText);
    Blockly.Xml.domToWorkspace(xml, workspace);
  }

  workspace.addChangeListener((event) => {
    if (event.isUiEvent || event.type === Blockly.Events.VIEWPORT_CHANGE) return;
    save();
  });

  document.getElementById('btn-save')?.addEventListener('click', save);
  document.getElementById('btn-load')?.addEventListener('click', load);
  document.getElementById('btn-clear')?.addEventListener('click', () => {
    workspace.clear();
    save();
  });

  document.getElementById('btn-export')?.addEventListener('click', () => {
    const pythonCode = Blockly.Python.workspaceToCode(workspace);
    const script = `"""Generated from Blockly Builder."""\n\n` +
`def run(ctx):\n` +
`    # Blockly-generated Python (review before production use):\n` +
`${pythonCode.split('\n').map(line => '    ' + line).join('\n')}\n` +
`\n    # keep chain alive\n` +
`    ctx.wait(0.1, next_step=0, desc=\"Blockly-driven loop\")\n`;

    const blob = new Blob([script], {type: 'text/x-python'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'blockly_generated.py';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });

  window.addEventListener('resize', () => Blockly.svgResize(workspace));
  setTimeout(() => Blockly.svgResize(workspace), 100);
})();
</script>
'''


def render(container: ui.element, ctx: PageContext) -> None:
    del ctx
    with container:
        ui.label("Blockly Visual Builder").classes("text-h6")
        ui.label(
            "Build script logic with Blockly, save/load workspace in browser storage, and export Python script stubs."
        ).classes("text-sm text-gray-600")
        ui.markdown(
            """
            **Notes**
            - Uses Blockly's built-in JSON serialization for save/load.
            - `Save Workspace` and autosave store data in your browser localStorage.
            - `Export Python` downloads a StepChain-compatible Python stub.
            """
        )
        ui.html(_BLOCKLY_HTML).classes("w-full")
