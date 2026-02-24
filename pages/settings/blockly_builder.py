from __future__ import annotations

import re
from pathlib import Path

from nicegui import ui

from layout.context import PageContext
from services.worker_commands import ScriptWorkerCommands as Commands


_BLOCKLY_HTML = r'''
<div class="w-full" style="height: 78vh; min-height: 560px; border: 1px solid #ddd; border-radius: 10px; overflow: hidden;">
  <div id="blockly-toolbar" style="display:flex; gap:8px; padding:10px; border-bottom:1px solid #eee; align-items:center; flex-wrap:wrap;">
    <button id="btn-save" style="padding:6px 10px; border:1px solid #bbb; border-radius:8px; background:#fff; cursor:pointer;">Save Workspace</button>
    <button id="btn-load" style="padding:6px 10px; border:1px solid #bbb; border-radius:8px; background:#fff; cursor:pointer;">Load Workspace</button>
    <button id="btn-clear" style="padding:6px 10px; border:1px solid #bbb; border-radius:8px; background:#fff; cursor:pointer;">Clear</button>
    <button id="btn-export" style="padding:6px 10px; border:1px solid #bbb; border-radius:8px; background:#fff; cursor:pointer;">Download Python</button>
    <span style="font-size:12px; color:#666;">Workspace key: <code>mes.blockly.workspace.v1</code></span>
  </div>
  <div id="blocklyDiv" style="height: calc(100% - 50px); width:100%;"></div>
</div>

<xml id="toolbox" style="display:none">
  <category name="MES" colour="#0ea5e9">
    <block type="mes_set_step_desc">
      <value name="TEXT"><shadow type="text"><field name="TEXT">ready</field></shadow></value>
    </block>
    <block type="mes_goto_step">
      <value name="STEP"><shadow type="math_number"><field name="NUM">10</field></shadow></value>
      <value name="DESC"><shadow type="text"><field name="TEXT">go next</field></shadow></value>
    </block>
    <block type="mes_wait_then_goto">
      <value name="SECONDS"><shadow type="math_number"><field name="NUM">1</field></shadow></value>
      <value name="NEXT_STEP"><shadow type="math_number"><field name="NUM">20</field></shadow></value>
      <value name="DESC"><shadow type="text"><field name="TEXT">waiting</field></shadow></value>
    </block>
    <block type="mes_notify">
      <field name="TYPE">info</field>
      <value name="TEXT"><shadow type="text"><field name="TEXT">hello</field></shadow></value>
    </block>
    <block type="mes_set_state">
      <value name="KEY"><shadow type="text"><field name="TEXT">status</field></shadow></value>
      <value name="VALUE"><shadow type="text"><field name="TEXT">running</field></shadow></value>
    </block>
    <block type="mes_vars_set">
      <value name="KEY"><shadow type="text"><field name="TEXT">counter</field></shadow></value>
      <value name="VALUE"><shadow type="math_number"><field name="NUM">0</field></shadow></value>
    </block>
    <block type="mes_vars_get">
      <value name="KEY"><shadow type="text"><field name="TEXT">counter</field></shadow></value>
      <value name="DEFAULT"><shadow type="math_number"><field name="NUM">0</field></shadow></value>
    </block>
    <block type="mes_vars_inc">
      <value name="KEY"><shadow type="text"><field name="TEXT">counter</field></shadow></value>
      <value name="AMOUNT"><shadow type="math_number"><field name="NUM">1</field></shadow></value>
      <value name="DEFAULT"><shadow type="math_number"><field name="NUM">0</field></shadow></value>
    </block>
    <block type="mes_log_info">
      <value name="TEXT"><shadow type="text"><field name="TEXT">debug</field></shadow></value>
    </block>
  </category>
  <category name="Logic" categorystyle="logic_category"></category>
  <category name="Loops" categorystyle="loop_category"></category>
  <category name="Math" categorystyle="math_category"></category>
  <category name="Text" categorystyle="text_category"></category>
  <category name="Lists" categorystyle="list_category"></category>
  <category name="Colour" categorystyle="colour_category"></category>
  <category name="Variables" categorystyle="variable_category"></category>
  <category name="Functions" categorystyle="procedure_category"></category>
</xml>
'''

_BLOCKLY_BOOTSTRAP_JS = r'''
(function() {
  if (window.__mesBlocklyBootstrapLoaded) {
    window.__mesInitBlockly?.();
    return;
  }
  window.__mesBlocklyBootstrapLoaded = true;

  const ensureScript = (src) => new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      if (existing.dataset.loaded === '1') {
        resolve();
      } else {
        existing.addEventListener('load', resolve, {once: true});
        existing.addEventListener('error', reject, {once: true});
      }
      return;
    }

    const tag = document.createElement('script');
    tag.src = src;
    tag.async = false;
    tag.addEventListener('load', () => {
      tag.dataset.loaded = '1';
      resolve();
    }, {once: true});
    tag.addEventListener('error', reject, {once: true});
    document.body.appendChild(tag);
  });

  const registerGenerator = (type, fn) => {
    if (Blockly.Python?.forBlock) {
      Blockly.Python.forBlock[type] = fn;
      return;
    }
    Blockly.Python[type] = function(block) {
      return fn(block, Blockly.Python);
    };
  };

  const registerMesBlocks = () => {
    if (window.__mesBlocklyBlocksRegistered) return;
    window.__mesBlocklyBlocksRegistered = true;

    Blockly.Blocks['mes_set_step_desc'] = {
      init: function() {
        this.appendValueInput('TEXT').appendField('ctx.set_step_desc');
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(200);
      }
    };
    registerGenerator('mes_set_step_desc', (block, generator) => {
      const text = generator.valueToCode(block, 'TEXT', generator.ORDER_NONE) || "''";
      return `ctx.set_step_desc(${text})\n`;
    });

    Blockly.Blocks['mes_goto_step'] = {
      init: function() {
        this.appendValueInput('STEP').appendField('ctx.goto step');
        this.appendValueInput('DESC').appendField('desc');
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(200);
      }
    };
    registerGenerator('mes_goto_step', (block, generator) => {
      const step = generator.valueToCode(block, 'STEP', generator.ORDER_NONE) || '0';
      const desc = generator.valueToCode(block, 'DESC', generator.ORDER_NONE) || "''";
      return `ctx.goto(int(${step}), desc=${desc})\n`;
    });

    Blockly.Blocks['mes_wait_then_goto'] = {
      init: function() {
        this.appendValueInput('SECONDS').appendField('if ctx.wait seconds');
        this.appendValueInput('NEXT_STEP').appendField('goto step');
        this.appendValueInput('DESC').appendField('desc');
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(200);
      }
    };
    registerGenerator('mes_wait_then_goto', (block, generator) => {
      const seconds = generator.valueToCode(block, 'SECONDS', generator.ORDER_NONE) || '0.1';
      const nextStep = generator.valueToCode(block, 'NEXT_STEP', generator.ORDER_NONE) || '0';
      const desc = generator.valueToCode(block, 'DESC', generator.ORDER_NONE) || "''";
      return `if ctx.wait(float(${seconds}), next_step=int(${nextStep}), desc=${desc}):\n    return\n`;
    });

    Blockly.Blocks['mes_notify'] = {
      init: function() {
        this.appendDummyInput().appendField('ctx.notify').appendField(new Blockly.FieldDropdown([
          ['info', 'info'],
          ['positive', 'positive'],
          ['warning', 'warning'],
          ['negative', 'negative']
        ]), 'TYPE');
        this.appendValueInput('TEXT').appendField('message');
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(200);
      }
    };
    registerGenerator('mes_notify', (block, generator) => {
      const type = block.getFieldValue('TYPE') || 'info';
      const text = generator.valueToCode(block, 'TEXT', generator.ORDER_NONE) || "''";
      return `ctx.notify(${text}, '${type}')\n`;
    });

    Blockly.Blocks['mes_set_state'] = {
      init: function() {
        this.appendValueInput('KEY').appendField('ctx.set_state key');
        this.appendValueInput('VALUE').appendField('value');
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(200);
      }
    };
    registerGenerator('mes_set_state', (block, generator) => {
      const key = generator.valueToCode(block, 'KEY', generator.ORDER_NONE) || "''";
      const value = generator.valueToCode(block, 'VALUE', generator.ORDER_NONE) || 'None';
      return `ctx.set_state(${key}, ${value})\n`;
    });

    Blockly.Blocks['mes_vars_set'] = {
      init: function() {
        this.appendValueInput('KEY').appendField('ctx.vars.set key');
        this.appendValueInput('VALUE').appendField('value');
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(200);
      }
    };
    registerGenerator('mes_vars_set', (block, generator) => {
      const key = generator.valueToCode(block, 'KEY', generator.ORDER_NONE) || "''";
      const value = generator.valueToCode(block, 'VALUE', generator.ORDER_NONE) || 'None';
      return `ctx.vars.set(${key}, ${value})\n`;
    });

    Blockly.Blocks['mes_vars_get'] = {
      init: function() {
        this.appendValueInput('KEY').appendField('ctx.vars.get key');
        this.appendValueInput('DEFAULT').appendField('default');
        this.setOutput(true, null);
        this.setColour(200);
      }
    };
    registerGenerator('mes_vars_get', (block, generator) => {
      const key = generator.valueToCode(block, 'KEY', generator.ORDER_NONE) || "''";
      const defaultValue = generator.valueToCode(block, 'DEFAULT', generator.ORDER_NONE) || 'None';
      const order = generator.ORDER_FUNCTION_CALL || generator.ORDER_ATOMIC || 0;
      return [`ctx.vars.get(${key}, ${defaultValue})`, order];
    });

    Blockly.Blocks['mes_vars_inc'] = {
      init: function() {
        this.appendValueInput('KEY').appendField('ctx.vars.inc key');
        this.appendValueInput('AMOUNT').appendField('amount');
        this.appendValueInput('DEFAULT').appendField('default');
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(200);
      }
    };
    registerGenerator('mes_vars_inc', (block, generator) => {
      const key = generator.valueToCode(block, 'KEY', generator.ORDER_NONE) || "''";
      const amount = generator.valueToCode(block, 'AMOUNT', generator.ORDER_NONE) || '1';
      const defaultValue = generator.valueToCode(block, 'DEFAULT', generator.ORDER_NONE) || '0';
      return `ctx.vars.inc(${key}, amount=float(${amount}), default=float(${defaultValue}))\n`;
    });

    Blockly.Blocks['mes_log_info'] = {
      init: function() {
        this.appendValueInput('TEXT').appendField('ctx.log_info');
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(200);
      }
    };
    registerGenerator('mes_log_info', (block, generator) => {
      const text = generator.valueToCode(block, 'TEXT', generator.ORDER_NONE) || "''";
      return `ctx.log_info(${text})\n`;
    });
  };

  window.__mesBlocklyBuildPythonScript = function() {
    if (!window.__mesBlocklyWorkspace || !window.Blockly?.Python) return '';

    const raw = String(Blockly.Python.workspaceToCode(window.__mesBlocklyWorkspace) || '').trim();
    const body = raw ? raw.split('\n').map((line) => `    ${line}`).join('\n') : '    pass';

    return `from __future__ import annotations\n\n` +
`from services.automation_runtime.context import PublicAutomationContext\n\n` +
`def main(ctx: PublicAutomationContext):\n` +
`    """Generated from Blockly Builder."""\n` +
`${body}\n\n` +
`# Export\n` +
`main = main\n`;
  };

  window.__mesInitBlockly = function() {
    if (!window.Blockly) {
      console.error('Blockly failed to load.');
      return;
    }

    const STORAGE_KEY = 'mes.blockly.workspace.v1';
    const host = document.getElementById('blocklyDiv');
    if (!host || host.dataset.blocklyReady === '1') return;

    registerMesBlocks();

    host.dataset.blocklyReady = '1';
    const workspace = Blockly.inject(host, {
      toolbox: document.getElementById('toolbox'),
      grid: {spacing: 20, length: 3, colour: '#ddd', snap: true},
      move: {scrollbars: true, drag: true, wheel: true},
      trashcan: true,
      zoom: {controls: true, wheel: true, startScale: 1.0, maxScale: 2, minScale: 0.3, scaleSpeed: 1.2},
      theme: Blockly.Themes.Zelos,
    });
    window.__mesBlocklyWorkspace = workspace;

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
      const xmlText = '<xml xmlns="https://developers.google.com/blockly/xml"><block type="mes_set_step_desc" x="30" y="30"><value name="TEXT"><shadow type="text"><field name="TEXT">blockly chain ready</field></shadow></value><next><block type="mes_wait_then_goto"><value name="SECONDS"><shadow type="math_number"><field name="NUM">0.2</field></shadow></value><value name="NEXT_STEP"><shadow type="math_number"><field name="NUM">0</field></shadow></value><value name="DESC"><shadow type="text"><field name="TEXT">loop</field></shadow></value></block></next></block></xml>';
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
      const script = window.__mesBlocklyBuildPythonScript();
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
  };

  Promise.resolve()
    .then(() => ensureScript('https://unpkg.com/blockly/blockly.min.js'))
    .then(() => ensureScript('https://unpkg.com/blockly/python_compressed'))
    .then(() => window.__mesInitBlockly())
    .catch((error) => console.error('Failed to bootstrap Blockly', error));
})();
'''


def _sanitize_script_name(raw: str) -> str:
    name = str(raw or '').strip().replace('\\', '/')
    if name.lower().endswith('.py'):
        name = name[:-3]
    name = re.sub(r'[^A-Za-z0-9_\-/]', '_', name)
    name = re.sub(r'/+', '/', name).strip('/')

    parts = [p for p in name.split('/') if p and p not in ('.', '..')]
    return '/'.join(parts)


def render(container: ui.element, ctx: PageContext) -> None:
    worker_handle = ctx.script_runtime or (ctx.workers.get('script_worker') if ctx.workers else None)
    client = ui.context.client

    with container:
        ui.label('Blockly Visual Builder').classes('text-h6')
        ui.label(
            'Build script logic with Blockly, then save directly to scripts/blockly with a runnable Automation Runtime signature.'
        ).classes('text-sm text-gray-600')
        ui.markdown(
            '''
            **Notes**
            - Includes custom `MES` blocks mapped to `PublicAutomationContext` methods from your codebase.
            - `Download Python` creates a local file in your browser.
            - `Export to scripts/blockly` writes server-side and hot-reloads that script.
            '''
        )

        with ui.row().classes('w-full items-end gap-2'):
            script_name_input = ui.input('Script name under scripts/blockly', value='generated_chain').classes('w-96')
            script_name_input.props('outlined dense')

            async def _export_to_scripts() -> None:
                safe_name = _sanitize_script_name(str(script_name_input.value or ''))
                if not safe_name:
                    ui.notify('Please provide a valid script name', type='negative')
                    return

                script = await client.run_javascript(
                    "return window.__mesBlocklyBuildPythonScript ? window.__mesBlocklyBuildPythonScript() : '';",
                    timeout=10.0,
                )
                if not isinstance(script, str) or not script.strip():
                    ui.notify('Blockly script is empty or not initialized', type='negative')
                    return

                out_path = Path('scripts') / 'blockly' / f'{safe_name}.py'
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(script, encoding='utf-8')

                script_runtime_name = f'blockly/{safe_name}'
                if worker_handle:
                    worker_handle.send(Commands.RELOAD_SCRIPT, script_name=script_runtime_name)
                    worker_handle.send(Commands.LIST_SCRIPTS)

                ui.notify(f'Exported: {out_path.as_posix()}', type='positive')

            ui.button('Export to scripts/blockly', on_click=_export_to_scripts).props('color=primary')

        ui.html(_BLOCKLY_HTML, sanitize=False).classes('w-full')
        ui.timer(0.05, lambda: ui.run_javascript(_BLOCKLY_BOOTSTRAP_JS), once=True)
