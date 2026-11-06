/* Milestone 10: separate preview-first advanced transform builder.
   In-memory draft undo/redo only; never writes to or modifies source CSV. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const ctx = () => window.DataMendryUI?.current?.() || {};
  const state = {dataset: null, edits: [[]], at: 0, reviewed: null, revision: 0};
  const clone = steps => steps.map(s => ({...s}));
  const stepsNow = () => state.edits[state.at];
  const short = s => `${s.action.replaceAll('_', ' ')} · ${s.column}` + (s.action === 'fill_blank' ? ` = ${s.value}` : s.action === 'replace_literal' ? ` · "${s.value}" → "${s.replacement}"` : s.action === 'round_number' ? ` · ${s.places} decimal places` : '');
  function status(message, bad=false) {
    $('advanced-status').textContent = message;
    $('advanced-status').classList.toggle('advanced-error', bad);
  }
  function resetPreview() {
    ++state.revision;
    state.reviewed = null;
    $('advanced-export').disabled = true;
    $('advanced-results').hidden = true;
  }
  function draw() {
    const active = Boolean(state.dataset);
    const steps = stepsNow();
    $('advanced-undo').disabled = state.at === 0;
    $('advanced-redo').disabled = state.at === state.edits.length - 1;
    $('advanced-clear').disabled = steps.length === 0;
    $('advanced-preview').disabled = !active || steps.length === 0;
    $('advanced-add').disabled = !active || steps.length >= 6;
    const list = $('advanced-steps'); list.replaceChildren();
    if (steps.length === 0) { const item=document.createElement('li'); item.textContent = 'No steps yet—choose an operation above.'; list.append(item); }
    for (const [index, step] of steps.entries()) {
      const item=document.createElement('li');
      const name=document.createElement('span'); name.textContent=short(step);
      const remove=document.createElement('button'); remove.type='button'; remove.className='button secondary advanced-remove'; remove.textContent='Remove'; remove.setAttribute('aria-label', `Remove step ${index+1}`);
      remove.addEventListener('click',()=> edit(steps.filter((_,i) => i !== index)));
      item.append(name,remove);list.append(item);
    }
  }
  function edit(newSteps) {
    resetPreview();
    state.edits=state.edits.slice(0,state.at+1);
    state.edits.push(clone(newSteps));
    if (state.edits.length>16) state.edits.shift();
    state.at=state.edits.length-1;
    draw();status('Plan changed. Preview the proposed result again before downloading.');
  }
  function syncDataset() {
    const active = ctx();
    if (active.id === state.dataset) return;
    state.dataset=active.id || null;
    state.edits=[[]];state.at=0; resetPreview();
    const col=$('advanced-column');col.replaceChildren();
    for (const name of (active.columns || [])) {
      const option=document.createElement('option');option.value=name;option.textContent=name;col.append(option);
    }
    draw(); status(active.id ? 'Choose a transformation and add a step.' : 'Upload or open a CSV to prepare a cleaning plan.');
  }
  function syncAction() {
    const value=$('advanced-action').value;
    $('advanced-value-wrap').hidden=!['fill_blank','replace_literal'].includes(value);
    $('advanced-replace-wrap').hidden=value!=='replace_literal';
    $('advanced-places-wrap').hidden=value!=='round_number';
    $('advanced-value-wrap').firstChild.textContent=value==='replace_literal'?'Find this exact text':'Fill blank cells with';
  }
  function getStep() {
    const action=$('advanced-action').value;
    const column=$('advanced-column').value;
    if (!state.dataset || !column) throw new Error('Load a CSV and select a column.');
    const value=['fill_blank','replace_literal'].includes(action)?$('advanced-value').value:'';
    const replacement=action==='replace_literal' ? $('advanced-replacement').value : '';
    const places=action==='round_number' ? Number($('advanced-places').value) : 0;
    if (action==='fill_blank' && !value.trim()) throw new Error('Enter a non-blank constant for empty cells.');
    if (action==='replace_literal' && !value) throw new Error('Enter the text to find.');
    return {action,column,value,replacement,places};
  }
  function tablePreview(container, columns, samples, side) {
    const table=document.createElement('table');
    const head=document.createElement('thead');const tr=document.createElement('tr');
    for (const col of columns){const th=document.createElement('th');th.textContent=col;tr.append(th);}
    head.append(tr);table.append(head);
    const body=document.createElement('tbody');
    for (const entry of samples){ const row=document.createElement('tr');
      entry[side].forEach((val,i)=>{const cell=document.createElement('td');cell.textContent=val??'';
        if (side==='after' && entry.changed_columns.includes(i)) cell.classList.add('advanced-changed');
        row.append(cell);});body.append(row);
    }
    table.append(body);$(container).replaceChildren(table);
  }
  async function api(action, payload) {
    const response=await fetch(`/api/datasets/${state.dataset}/advanced/${action}`,{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)
    });
    if (!response.ok) {
      let problem=`${action} failed (${response.status}).`;
      try {const body=await response.json();if(typeof body.detail==='string') problem=body.detail;} catch{}
      throw new Error(problem);
    }
    return response;
  }
  $('advanced-action').addEventListener('change',syncAction);
  $('advanced-add').addEventListener('click',()=>{
    try {if (stepsNow().length >= 6) throw new Error('Maximum six steps.');edit([...stepsNow(),getStep()]);}
    catch(error){status(error.message,true);}
  });
  $('advanced-clear').addEventListener('click',()=>edit([]));
  $('advanced-undo').addEventListener('click',()=>{if(!state.at)return;state.at--;resetPreview();draw();status('Draft plan reverted. Preview again before export.');});
  $('advanced-redo').addEventListener('click',()=>{if(state.at>=state.edits.length-1)return;state.at++;resetPreview();draw();status('Draft plan restored. Preview again before export.');});
  $('advanced-preview').addEventListener('click',async()=>{
    const dataset=state.dataset, revision=state.revision, steps=clone(stepsNow());
    $('advanced-preview').disabled=true;status('Calculating proposed changes…');
    try {
      const response=await api('preview',{steps});const data=await response.json();
      if (dataset!==state.dataset || revision!==state.revision) return;
      state.reviewed={dataset,steps,preview_token:data.preview_token};
      $('advanced-export').disabled=false;
      const metric=$('advanced-metrics');metric.replaceChildren();
      for (const [name,num] of [['Rows inspected',data.row_count],['Changed cells',data.changed_cells],['Nonnumeric skips',data.skipped_numeric]]) {
        const item=document.createElement('div');const text=document.createElement('small');text.textContent=name;const value=document.createElement('strong');value.textContent=Number(num).toLocaleString();item.append(text,value);metric.append(item);
      }
      $('advanced-notes').textContent=(data.warnings||[]).join(' · ')||'No warnings. Original CSV unchanged.';
      tablePreview('advanced-before',data.columns,data.rows,'before');
      tablePreview('advanced-after',data.columns,data.rows,'after');
      $('advanced-results').hidden=false;
      status(`Preview completed: ${data.row_count.toLocaleString()} rows · ${data.changed_cells.toLocaleString()} changed cells. Review before downloading.`);
    } catch(error){ if(dataset===state.dataset) status(error.message,true);}
    finally {draw();}
  });
  $('advanced-export').addEventListener('click',async()=>{
    const last=state.reviewed;
    if (!last || last.dataset!==state.dataset) return status('Preview the current plan before downloading.',true);
    $('advanced-export').disabled=true;status('Preparing a separate CSV download…');
    try{
      const response=await api('export',{steps:last.steps,preview_token:last.preview_token});
      const blob=await response.blob();
      if (last.dataset!==state.dataset || state.reviewed!==last) return;
      const url=URL.createObjectURL(blob); const a=document.createElement('a');
      a.href=url;a.download='datamendry-advanced-cleaned.csv';a.click();
      setTimeout(()=>URL.revokeObjectURL(url),10000);
      status('Separate CSV downloaded. Your original remains unchanged.');
    }catch(error){status(error.message,true);}
    finally{ $('advanced-export').disabled=!(state.reviewed && state.reviewed===last);}
  });
  window.addEventListener('datamendry:dataset', syncDataset);
  syncAction();syncDataset();
})();
