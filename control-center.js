/* Four control workflows for the existing Ted Board shell. */
'use strict';

class ControlCenter {
 constructor({api,getCards,answer,reloadCards,redraw,select,notice}) {
  this.api=async(...args)=>{const generation=this.generation;const result=await api(...args);if(generation!==this.generation)throw new Error('Control request belongs to a previous key');return result};this.getCards=getCards;this.answer=answer;this.reloadCards=reloadCards;
  this.redraw=redraw;this.select=select;this.notice=notice;
  this.generation=0;this.reset();
  this.clock=setInterval(()=>this.tick(),1000);
 }
 reset(){
  this.generation++;
  this.view='Veto';this.vetoes=[];this.rules=[];this.loaded=false;this.loading=false;
  this.serverOffset=0;this.fallbackExpiry=new Map();this.busy=false;this.ruleCardId=null;
  this.ruleDraft=null;this.ruleEditDraft=null;this.editingRuleId=null;this.deletingRuleId=null;
  this.batchSelection=new Map();this.sprint={phase:'ready',endsAt:0,startedAt:0,queue:[],cleared:0,skipped:0,pending:false};
 }
 node(tag,cls,value){const node=document.createElement(tag);if(cls)node.className=cls;if(value!==undefined)node.textContent=String(value);return node}
 button(label,cls,fn){const node=this.node('button',cls,label);node.type='button';node.addEventListener('click',fn);return node}
 needs(){return this.getCards().filter(card=>card.section==='needs_you')}
 kind(card){return ['send_email','spend_money','approve_design','other'].includes(card.decision_kind)?card.decision_kind:null}
 kindName(kind){if(kind==='')return 'All kinds';return ({send_email:'Email',spend_money:'Spending',approve_design:'Design',other:'Other'})[kind]||'Other'}
 formatMoney(cents,currency){try{return new Intl.NumberFormat(undefined,{style:'currency',currency}).format(cents/100)}catch{return `${currency} ${(cents/100).toFixed(2)}`}}
 now(){return Date.now()+this.serverOffset}
 expiry(veto){const parsed=Date.parse(veto.due_at||veto.expires_at);if(Number.isFinite(parsed))return parsed;
  if(!this.fallbackExpiry.has(veto.card_id))this.fallbackExpiry.set(veto.card_id,this.now()+7200000);
  return this.fallbackExpiry.get(veto.card_id)}
 duration(seconds){const h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60),s=seconds%60;return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`}
 async load(){if(this.loading)return;const generation=this.generation;this.loading=true;this.redraw();
  try{const data=await this.api('GET',undefined,'control');if(generation!==this.generation)return;
   if(!Array.isArray(data.vetoes)||!Array.isArray(data.rules))throw new Error('Control data could not be read. Refresh to try again.');
   this.vetoes=data.vetoes;this.rules=data.rules;this.loaded=true;
   const serverTime=Date.parse(data.server_time);this.serverOffset=Number.isFinite(serverTime)?serverTime-Date.now():0;
   this.redraw();
  }catch(error){if(generation===this.generation){this.notice(error.message,true);this.redraw()}}finally{if(generation===this.generation)this.loading=false}
 }
 open(view){this.view=view;this.select();this.load()}
 openRule(card){this.ruleCardId=card.id;this.ruleDraft={answer_action:null,answer_text:'',choice_value:'',sentence:'',scope_project:card.project||'',scope_kind:this.kind(card)||'other',exampleIds:new Set([card.id])};this.open('Rules')}
 render(main){
  const shell=this.node('div','control-center');
  const header=this.node('header','control-head');header.append(this.node('h2',null,'less on your plate.'),this.node('p',null,'Four ways to keep decisions moving. Your recorded choices stay visible.'));shell.append(header);
  const nav=this.node('nav','control-nav');nav.setAttribute('aria-label','Control views');
  for(const name of ['Veto','Rules','Sprint','Batches']){const b=this.button(name,'control-nav-button',()=>{this.view=name;this.redraw()});b.setAttribute('aria-current',String(this.view===name));nav.append(b)}shell.append(nav);
  const content=this.node('section','control-content');content.setAttribute('aria-label',this.view);
  if(this.view==='Veto')this.renderVeto(content);
  if(this.view==='Rules')this.renderRules(content);
  if(this.view==='Sprint')this.renderSprint(content);
  if(this.view==='Batches')this.renderBatches(content);
  shell.append(content);main.append(shell);
 }
 heading(parent,title,description){const head=this.node('div','control-view-head');head.append(this.node('h3',null,title),this.node('p',null,description));parent.append(head)}
 empty(parent,text){parent.append(this.node('p','control-empty',text))}
 renderVeto(parent){
  this.heading(parent,'Only stop what looks wrong','Drafts wait for a timed worker review. The board shows the brake; it does not send or spend.');
  const held=this.node('p','veto-held');held.append(this.node('strong',null,'Held for you. '),document.createTextNode('Contracts and signatures, spending, pricing or scope commitments, legal matters, new external people, production database writes, and App Store submits stay with you. No timer.'));parent.append(held);
  if(!this.loaded){this.empty(parent,this.loading?'Opening timed drafts…':'Timed drafts could not be loaded. Tap Refresh to try again.');return}
  if(!this.vetoes.length){this.empty(parent,'No timed drafts are waiting.');return}
  const list=this.node('div','veto-list');
  for(const veto of this.vetoes){const row=this.node('article','veto-row');row.dataset.vetoCardId=veto.card_id;
   const main=this.node('div','veto-main');const top=this.node('div','veto-top');top.append(this.node('h4',null,veto.planned_action||this.getCards().find(c=>c.id===veto.card_id)?.title||'Planned action'));
   if(Number.isFinite(Number(veto.confidence))&&veto.confidence!==null){const raw=Number(veto.confidence);top.append(this.node('span','control-confidence',`${Math.round(raw<=1?raw*100:raw)}% confidence`))}
   main.append(top);if(veto.draft_text)main.append(this.node('p','veto-draft',veto.draft_text));
   const side=this.node('div','veto-side');const status=String(veto.status||'pending').toLowerCase();const left=Math.max(0,Math.ceil((this.expiry(veto)-this.now())/1000));
   const clock=this.node('time','veto-clock');clock.dataset.vetoClock=veto.card_id;
   if(status==='stopped'){clock.textContent='stopped';row.dataset.vetoStatus='stopped'}
   else if(status==='cleared'){clock.textContent='cleared by worker';row.dataset.vetoStatus='cleared'}
   else if(status!=='pending'){clock.textContent=status.replaceAll('_',' ');row.dataset.vetoStatus=status}
   else if(left===0){clock.textContent='time up, waiting for worker clearance';row.dataset.vetoStatus='elapsed'}
   else{clock.textContent=this.duration(left);clock.dateTime=veto.due_at||veto.expires_at||'';row.dataset.vetoStatus='pending'}
   const stop=this.button('Stop','control-stop',()=>this.stopVeto(veto));stop.disabled=this.busy||!['pending','elapsed','cleared'].includes(status);
   side.append(clock,stop);row.append(main,side);list.append(row)
  }parent.append(list);
 }
 async stopVeto(veto){if(this.busy||!['pending','elapsed','cleared'].includes(veto.status))return;this.busy=true;this.redraw();
  try{const data=await this.api('POST',{action:'veto_stop',card_id:veto.card_id,revision:veto.revision});
   if(!data.ok||!data.veto)throw new Error('Stop was not confirmed. Refresh to check this draft.');
   this.vetoes=this.vetoes.map(item=>item.card_id===veto.card_id?data.veto:item);
   this.notice('Draft stopped.');await this.reloadCards();
  }catch(error){this.notice(error.message,true);await this.load()}finally{this.busy=false;this.redraw()}
 }
 tick(){
  if(this.sprint.phase==='running'&&this.now()>=this.sprint.endsAt){this.sprint.phase='done';this.redraw();return}
  if(this.sprint.phase==='running'){const timer=document.querySelector('[data-sprint-timer]');if(timer)timer.textContent=this.sprintTime()}
  if(this.view!=='Veto')return;
  for(const veto of this.vetoes){if(veto.status!=='pending')continue;const row=[...document.querySelectorAll('[data-veto-card-id]')].find(el=>el.dataset.vetoCardId===veto.card_id);if(!row)continue;
   const clock=row.querySelector('[data-veto-clock]');if(!clock)continue;const left=Math.max(0,Math.ceil((this.expiry(veto)-this.now())/1000));
   clock.textContent=left?this.duration(left):'time up, waiting for worker clearance';
   row.dataset.vetoStatus=left?'pending':'elapsed';row.querySelector('.control-stop').disabled=this.busy;
  }
 }
 renderRules(parent){
  this.heading(parent,'Decisions I can remember','Answer a card once, then give the rule a narrow scope you can change later.');
  if(!this.loaded){this.empty(parent,this.loading?'Opening the rulebook…':'Rules could not be loaded. Tap Refresh to try again.');return}
  if(this.ruleCardId){const card=this.needs().find(c=>c.id===this.ruleCardId);if(card)this.renderRuleCreate(parent,card);else{this.ruleCardId=null;this.ruleDraft=null}}
  const book=this.node('div','rulebook');const head=this.node('div','rulebook-heading');head.append(this.node('h4',null,'The rulebook'),this.node('span',null,`${this.rules.length} ${this.rules.length===1?'rule':'rules'}`));book.append(head);
  if(!this.rules.length)this.empty(book,'No rules yet. Open a Needs you card and choose Make this a rule.');
  for(const rule of this.rules)book.append(this.renderRuleRow(rule));parent.append(book);
 }
 field(label,value,name){const wrap=this.node('label','control-field');wrap.append(this.node('span',null,label));const input=this.node('input');input.type='text';input.value=value||'';input.setAttribute('aria-label',name||label);wrap.append(input);return {wrap,input}}
 scopeSelect(type,value){const select=this.node('select');select.setAttribute('aria-label',type==='project'?'Project scope':'Decision kind scope');
  const options=type==='project'?[['','All projects'],...[...new Set(this.getCards().map(c=>c.project).filter(Boolean))].map(p=>[p,p])]:[['','All kinds'],['send_email','Email'],['spend_money','Spending'],['approve_design','Design'],['other','Other']];
  if(value&&!options.some(([v])=>v===value))options.push([value,value]);
  for(const [v,label] of options){const o=this.node('option',null,label);o.value=v;select.append(o)}select.value=value??'';return select
 }
 renderRuleCreate(parent,card){
  const draft=this.ruleDraft||{answer_action:null,answer_text:'',choice_value:'',sentence:'',scope_project:card.project||'',scope_kind:this.kind(card)||'other',exampleIds:new Set([card.id])};this.ruleDraft=draft;
  const form=this.node('form','rule-create');form.setAttribute('aria-label','Make this a rule');
  form.append(this.node('h4',null,'One answer, then a rule'),this.node('p','control-subtle',card.title));
  const choices=(Array.isArray(card.options)?card.options:[]).map(option=>typeof option==='string'?{label:option,value:option}:option).filter(option=>option&&typeof option.label==='string'&&typeof option.value==='string');
  const answer=this.field('Answer this card',draft.answer_text);answer.input.maxLength=2000;answer.input.addEventListener('input',()=>draft.answer_text=answer.input.value);
  if(choices.length){
   const group=this.node('fieldset','rule-answer-options');group.append(this.node('legend',null,'Answer this card'));
   for(const option of choices){const label=this.node('label');const input=this.node('input');input.type='radio';input.name='rule-answer';input.value=option.value;input.checked=draft.answer_action==='choice'&&draft.choice_value===option.value;input.addEventListener('change',()=>{draft.answer_action='choice';draft.choice_value=option.value;answer.input.disabled=true});label.append(input,this.node('span',null,option.label));group.append(label)}
   const noteLabel=this.node('label');const noteRadio=this.node('input');noteRadio.type='radio';noteRadio.name='rule-answer';noteRadio.value='note';noteRadio.checked=draft.answer_action==='note';noteRadio.addEventListener('change',()=>{draft.answer_action='note';answer.input.disabled=false;answer.input.focus()});noteLabel.append(noteRadio,this.node('span',null,'Write a note'));group.append(noteLabel);form.append(group);
   answer.input.disabled=draft.answer_action!=='note';
  }else draft.answer_action='note';
  answer.input.required=draft.answer_action==='note';form.append(answer.wrap);
  const sentence=this.field('Rule sentence',draft.sentence);sentence.input.required=true;sentence.input.maxLength=500;sentence.input.addEventListener('input',()=>draft.sentence=sentence.input.value);form.append(sentence.wrap);
  const scope=this.node('div','rule-scopes');const project=this.scopeSelect('project',draft.scope_project),kind=this.scopeSelect('kind',draft.scope_kind);
  project.addEventListener('change',()=>{draft.scope_project=project.value;this.updateRulePreview(form,card,draft)});
  kind.addEventListener('change',()=>{draft.scope_kind=kind.value;this.updateRulePreview(form,card,draft)});
  scope.append(project,kind);form.append(scope);
  const preview=this.node('div','rule-preview');preview.dataset.rulePreview='';form.append(preview);this.updateRulePreview(form,card,draft);
  const actions=this.node('div','control-actions');const save=this.button('Save answer and rule','primary',()=>{});save.type='submit';save.disabled=this.busy;
  actions.append(save,this.button('Cancel','quiet',()=>{this.ruleCardId=null;this.ruleDraft=null;this.redraw()}));form.append(actions);
  form.addEventListener('submit',event=>{event.preventDefault();this.createRule(card,draft)});parent.append(form)
 }
 ruleScopeMatches(card,project,kind){return (!project||card.project===project)&&(!kind||(this.kind(card)||'other')===kind)}
 exampleCards(draft,sourceId,editing=false){const selected=draft.exampleIds||new Set([sourceId]);const source=this.getCards().find(card=>card.id===sourceId);
  const candidates=this.getCards().filter(card=>card.id!==sourceId&&this.ruleScopeMatches(card,draft.scope_project,draft.scope_kind)&&(editing?(card.section==='needs_you'||selected.has(card.id)):card.section==='needs_you'));
  return [...(source&&(!editing||this.ruleScopeMatches(source,draft.scope_project,draft.scope_kind))?[source]:[]),...candidates]
 }
 updateRulePreview(form,source,draft,editing=false){const preview=form.querySelector('[data-rule-preview]');if(!preview)return;
  const sourceId=typeof source==='string'?source:source?.id;draft.exampleIds||=new Set(sourceId?[sourceId]:[]);if(!editing&&sourceId)draft.exampleIds.add(sourceId);
  preview.replaceChildren(this.node('p',null,'Confirm examples'),this.node('small',null,editing?'Check cards that would match the revised rule. You can confirm none if no current cards fit.':'Check cards that would match this rule. Scope alone does not prove a match. The source card stays selected.'));
  const cards=this.exampleCards(draft,sourceId,editing);const list=this.node('div','rule-example-list');
  for(const card of cards){const label=this.node('label','rule-example-option');label.dataset.ruleExampleId=card.id;
   const input=this.node('input');input.type='checkbox';input.checked=draft.exampleIds.has(card.id);input.disabled=(!editing&&card.id===sourceId)||!Number.isInteger(card.revision);
   input.addEventListener('change',()=>{if(input.checked){if(draft.exampleIds.size>=10){input.checked=false;this.notice('Choose up to 10 examples.',true);return}draft.exampleIds.add(card.id)}else draft.exampleIds.delete(card.id);if(editing){draft.confirmed=false;const confirm=form.querySelector('[data-example-confirm]');if(confirm)confirm.checked=false}});
   const copy=this.node('span');copy.append(this.node('strong',null,card.title),this.node('small',null,`${card.project||'Unknown project'}${card.id===sourceId?' · source card':''}${!Number.isInteger(card.revision)?' · no revision':''}`));label.append(input,copy);list.append(label)
  }
  if(!cards.length)list.append(this.node('p','control-subtle',editing?'No current cards fit this scope. Confirm zero examples to save the rule.':'The source card is unavailable. Refresh the board before saving.'));
  preview.append(list);
  if(!editing&&source&&typeof source!=='string'&&!this.ruleScopeMatches(source,draft.scope_project,draft.scope_kind))preview.append(this.node('small','rule-example-warning','The source card is outside this scope. Widen the scope before saving.'))
 }
 examplePayload(draft,sourceId,editing=false){const source=this.getCards().find(card=>card.id===sourceId);if(!editing&&(!source||!this.ruleScopeMatches(source,draft.scope_project,draft.scope_kind)))return null;
  const ids=editing?[...(draft.exampleIds||[])]:[sourceId,...[...(draft.exampleIds||[])].filter(id=>id!==sourceId)];if(ids.length>(10)||!editing&&ids.length<1)return null;
  const allowed=new Set(this.exampleCards(draft,sourceId,editing).map(card=>card.id));const examples=[];
  for(const id of ids){const card=this.getCards().find(item=>item.id===id);if(!card||!allowed.has(id)||!Number.isInteger(card.revision)||!this.ruleScopeMatches(card,draft.scope_project,draft.scope_kind))return null;examples.push({id,revision:card.revision})}return examples
 }
 async createRule(card,draft){if(this.busy)return;const choices=(Array.isArray(card.options)?card.options:[]).map(option=>typeof option==='string'?{label:option,value:option}:option).filter(option=>option&&typeof option.label==='string'&&typeof option.value==='string');
  const answerAction=draft.answer_action,answer=answerAction==='choice'?draft.choice_value:draft.answer_text.trim(),sentence=draft.sentence.trim();
  if(!sentence||answerAction==='note'&&!answer||answerAction==='choice'&&!choices.some(option=>option.value===answer)||!['note','choice'].includes(answerAction)){this.notice('Choose an answer and write the rule sentence first.',true);return}
  const examples=this.examplePayload(draft,card.id);if(!examples){this.notice('Confirm current examples in this scope before saving.',true);return}
  this.busy=true;this.redraw();try{const data=await this.api('POST',{action:'rule_create',card_id:card.id,answer_action:answerAction,answer_text:answer,sentence,scope_project:draft.scope_project,scope_kind:draft.scope_kind,examples});
   if(!data.ok||!data.rule)throw new Error('Rule was not confirmed. Refresh before trying again.');
   this.rules=[data.rule,...this.rules.filter(rule=>rule.id!==data.rule.id)];this.ruleCardId=null;this.ruleDraft=null;
   this.notice('Answer and rule saved.');await this.reloadCards();
  }catch(error){this.notice(error.message,true);await this.load()}finally{this.busy=false;this.redraw()}
 }
 renderRuleRow(rule){const row=this.node('article','rule-row');row.dataset.ruleId=rule.id;row.dataset.enabled=String(Boolean(rule.enabled));
  const meta=this.node('div','rule-meta');meta.append(this.node('span',null,rule.scope_project||'All projects'),this.node('span',null,this.kindName(rule.scope_kind||'')),this.node('span',null,`${Number(rule.match_count??rule.matched_count)||0} matched`));
  row.append(meta,this.node('h5',null,rule.sentence||'Untitled rule'));
  const examples=this.node('div','rule-examples');examples.append(this.node('p',null,'Confirmed examples'));const list=this.node('ul');for(const example of (Array.isArray(rule.examples)?rule.examples:[]).slice(0,10)){list.append(this.node('li',null,typeof example==='string'?example:example.card_title||example.title||'Example card'))}if(!list.children.length)list.append(this.node('li',null,'No examples confirmed yet.'));examples.append(list);row.append(examples);
  if(this.editingRuleId===rule.id)this.renderRuleEdit(row,rule);
  else{const actions=this.node('div','rule-actions');const toggle=this.button(rule.enabled?'On':'Off','rule-switch',()=>this.updateRule(rule,{enabled:!rule.enabled}));toggle.setAttribute('role','switch');toggle.setAttribute('aria-checked',String(Boolean(rule.enabled)));toggle.setAttribute('aria-label','Rule enabled');toggle.disabled=this.busy;actions.append(toggle,this.button('Edit rule','',()=>{this.editingRuleId=rule.id;this.ruleEditDraft=null;this.redraw()}),this.button('Delete rule','quiet',()=>{this.deletingRuleId=rule.id;this.redraw()}));row.append(actions)}
  if(this.deletingRuleId===rule.id){const confirm=this.node('div','rule-delete-confirm');confirm.append(this.node('p',null,'Delete this rule? Future decisions will no longer use it.'),this.button('Confirm delete','control-danger',()=>this.deleteRule(rule)),this.button('Keep rule','quiet',()=>{this.deletingRuleId=null;this.redraw()}));row.append(confirm)}
  return row
 }
 renderRuleEdit(row,rule){const sourceId=rule.source_card_id||rule.examples?.[0]?.id;
  const savedExamples=(Array.isArray(rule.examples)?rule.examples:[]).map(example=>example.id).filter(id=>{const card=this.getCards().find(item=>item.id===id);return card&&this.ruleScopeMatches(card,rule.scope_project||'',rule.scope_kind||'')});
  const draft=this.ruleEditDraft||{sentence:rule.sentence||'',scope_project:rule.scope_project||'',scope_kind:rule.scope_kind||'',exampleIds:new Set(savedExamples),confirmed:false};this.ruleEditDraft=draft;
  const form=this.node('form','rule-edit');const sentence=this.field('Rule sentence',draft.sentence);sentence.input.required=true;sentence.input.maxLength=500;
  const resetConfirmation=()=>{draft.confirmed=false;const confirm=form.querySelector('[data-example-confirm]');if(confirm)confirm.checked=false};
  sentence.input.addEventListener('input',()=>{draft.sentence=sentence.input.value;resetConfirmation()});form.append(sentence.wrap);
  const scopes=this.node('div','rule-scopes');const project=this.scopeSelect('project',draft.scope_project),kind=this.scopeSelect('kind',draft.scope_kind);
  const scopeChanged=()=>{draft.scope_project=project.value;draft.scope_kind=kind.value;for(const id of draft.exampleIds){const card=this.getCards().find(item=>item.id===id);if(!card||!this.ruleScopeMatches(card,draft.scope_project,draft.scope_kind))draft.exampleIds.delete(id)}resetConfirmation();this.updateRulePreview(form,sourceId,draft,true)};
  project.addEventListener('change',scopeChanged);kind.addEventListener('change',scopeChanged);scopes.append(project,kind);form.append(scopes);
  const preview=this.node('div','rule-preview');preview.dataset.rulePreview='';form.append(preview);this.updateRulePreview(form,sourceId,draft,true);
  const confirmLabel=this.node('label','rule-confirm');const confirm=this.node('input');confirm.type='checkbox';confirm.checked=Boolean(draft.confirmed);confirm.dataset.exampleConfirm='';confirm.addEventListener('change',()=>draft.confirmed=confirm.checked);confirmLabel.append(confirm,this.node('span',null,'I confirm these examples match the rule'));form.append(confirmLabel);
  const actions=this.node('div','control-actions');const save=this.button('Save rule','primary',()=>{});save.type='submit';save.disabled=this.busy;actions.append(save,this.button('Cancel edit','quiet',()=>{this.editingRuleId=null;this.ruleEditDraft=null;this.redraw()}));form.append(actions);
  form.addEventListener('submit',event=>{event.preventDefault();if(!draft.confirmed){this.notice('Confirm which current cards match this rule before saving.',true);return}const examples=this.examplePayload(draft,sourceId,true);if(!examples){this.notice('Refresh the board and confirm current examples before saving.',true);return}this.updateRule(rule,{sentence:draft.sentence.trim(),scope_project:draft.scope_project,scope_kind:draft.scope_kind,enabled:Boolean(rule.enabled),examples})});row.append(form)
 }
 async updateRule(rule,changes){if(this.busy)return;if('sentence' in changes&&!changes.sentence){this.notice('Write a rule sentence first.',true);return}this.busy=true;
  try{const payload={action:'rule_update',rule_id:rule.id,sentence:changes.sentence??rule.sentence,scope_project:changes.scope_project??rule.scope_project??'',scope_kind:changes.scope_kind??rule.scope_kind??'',enabled:changes.enabled??Boolean(rule.enabled)};if('examples' in changes)payload.examples=changes.examples;
   const data=await this.api('POST',payload);
   if(!data.ok||!data.rule)throw new Error('Rule change was not confirmed. Refresh to check it.');this.rules=this.rules.map(item=>item.id===rule.id?data.rule:item);this.editingRuleId=null;this.ruleEditDraft=null;this.notice('Rule saved.');
  }catch(error){this.notice(error.message,true);await this.load()}finally{this.busy=false;this.redraw()}
 }
 async deleteRule(rule){if(this.busy)return;this.busy=true;
  try{const data=await this.api('POST',{action:'rule_delete',rule_id:rule.id});if(!data.ok||data.rule_id!==rule.id)throw new Error('Delete was not confirmed. Refresh to check it.');this.rules=this.rules.filter(item=>item.id!==rule.id);this.deletingRuleId=null;this.notice('Rule deleted.');
  }catch(error){this.notice(error.message,true);await this.load()}finally{this.busy=false;this.redraw()}
 }
 sprintItems(){return this.needs().map(card=>{const value=Number(card.priority_value),effort=Number(card.effort_seconds);const valueEstimated=card.priority_value===null||card.priority_value===undefined||card.priority_value===''||!Number.isFinite(value)||value<0,effortEstimated=!(effort>0);return {card,value:valueEstimated?1:value,effort:effortEstimated?60:effort,valueEstimated,effortEstimated}}).sort((a,b)=>b.value/b.effort-a.value/a.effort||a.card.title.localeCompare(b.card.title))}
 sprintTime(){const seconds=Math.max(0,Math.ceil((this.sprint.endsAt-this.now())/1000));return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`}
 sprintLeft(){return Math.max(0,Math.ceil((this.sprint.endsAt-this.now())/1000))}
 currentSprintItem(){const items=this.sprintItems();for(const id of this.sprint.queue){const item=items.find(row=>row.card.id===id);if(item)return item}return null}
 renderSprint(parent){this.heading(parent,'Give me five minutes','One decision at a time, ordered by priority value per second. Missing values or effort use labeled estimates; recorded fields stay recorded.');
  const score=this.node('p','sprint-score',`${this.sprint.cleared} cleared · ${this.sprint.skipped} skipped`);
  const clock=this.node('div','sprint-clock');const time=this.node('strong',null,this.sprint.phase==='ready'?'5:00':this.sprint.phase==='running'?this.sprintTime():'0:00');time.dataset.sprintTimer='';clock.append(time,this.node('span',null,'Your five-minute window'));parent.append(clock);
  if(this.sprint.phase==='ready'){
   const start=this.button('Start 5:00','primary sprint-start',()=>this.startSprint());start.disabled=!this.sprintItems().length;parent.append(start);
   if(!this.sprintItems().length)this.empty(parent,'No decisions need you right now.');
   const preview=this.node('div','sprint-preview');preview.append(this.node('h4',null,'Your next best seconds'));const list=this.node('ol');
   for(const item of this.sprintItems().slice(0,5)){const row=this.node('li');row.append(this.node('span',null,item.card.title),this.node('small',null,`${item.value} ${item.valueEstimated?'estimated':'priority'} points / ${item.effort}s${item.effortEstimated?' estimated':''}`));list.append(row)}preview.append(list);parent.append(preview);return
  }
  parent.append(score);
  if(this.sprint.phase==='done'){const used=Math.min(300,Math.max(0,Math.ceil((Math.min(this.now(),this.sprint.endsAt)-this.sprint.startedAt)/1000)));parent.append(this.node('p','sprint-result',`Time used ${Math.floor(used/60)}:${String(used%60).padStart(2,'0')}. ${this.sprint.cleared} cleared, ${this.sprint.skipped} skipped.`));parent.append(this.button('Reset sprint','',()=>{this.sprint={phase:'ready',endsAt:0,startedAt:0,queue:[],cleared:0,skipped:0,pending:false};this.redraw()}));return}
  const active=this.node('div','sprint-active');active.dataset.sprintActive='';const item=this.currentSprintItem();
  if(!item)this.empty(active,'No decisions remain in this sprint.');
  else{const card=item.card;const article=this.node('article','sprint-question');article.append(this.node('p','sprint-kind',`${card.project} · ${this.kindName(this.kind(card))}`),this.node('h4',null,card.title));if(card.body)article.append(this.node('p','sprint-body',card.body));article.append(this.node('p','sprint-estimate',`${item.value} ${item.valueEstimated?'estimated':'priority'} points / ${item.effort}s${item.effortEstimated?' estimated':''}`));
   const opts=(Array.isArray(card.options)?card.options:[]).slice(0,4).map(option=>typeof option==='string'?{label:option,value:option}:option).filter(option=>option&&typeof option.label==='string'&&typeof option.value==='string');
   if(opts.length){const actions=this.node('div','sprint-choices');for(const option of opts){const choice=this.button(option.label,'primary',()=>this.sprintAnswer(card,'choice',option.value));choice.disabled=this.sprint.pending;actions.append(choice)}article.append(actions)}
   const form=this.node('form','sprint-note');const input=this.node('textarea');input.setAttribute('aria-label','Answer for '+card.title);input.placeholder='or tell Ted what to do';input.maxLength=2000;const send=this.button('Send answer','',()=>{});send.type='submit';send.disabled=this.sprint.pending;form.append(input,send);form.addEventListener('submit',event=>{event.preventDefault();if(input.value.trim())this.sprintAnswer(card,'note','',input.value.trim());else{this.notice('Write an answer first.',true);input.focus()}});article.append(form);
   const skip=this.button('Skip for now','quiet',()=>{this.sprint.queue=this.sprint.queue.filter(id=>id!==card.id);this.sprint.skipped++;this.redraw()});skip.disabled=this.sprint.pending;article.append(skip);active.append(article)}
  parent.append(active,this.button('End sprint','quiet sprint-end',()=>this.endSprint()));
 }
 startSprint(){if(this.sprint.phase!=='ready')return;const now=this.now();this.sprint={phase:'running',startedAt:now,endsAt:now+300000,queue:this.sprintItems().map(item=>item.card.id),cleared:0,skipped:0,pending:false};this.redraw()}
 endSprint(){if(this.sprint.phase!=='running')return;this.sprint.phase='done';this.sprint.endsAt=Math.min(this.sprint.endsAt,this.now());this.redraw()}
 async sprintAnswer(card,action,value='',note=''){if(this.sprint.phase!=='running'||this.sprint.pending||this.sprintLeft()===0)return;this.sprint.pending=true;this.redraw();
  try{const confirmed=await this.answer(card,action,value,note);if(confirmed){this.sprint.cleared++;this.sprint.queue=this.sprint.queue.filter(id=>id!==card.id)}}finally{this.sprint.pending=false;this.redraw()}
 }
 batchEligible(card){if(!this.kind(card)||!Number.isInteger(card.revision)||card.revision<0)return false;if(card.decision_kind!=='spend_money')return true;
  return Number.isInteger(Number(card.amount_cents))&&Number(card.amount_cents)>0&&/^[A-Z]{3}$/.test(String(card.currency||''))}
 imageURL(raw){try{const url=new URL(raw);return ['https:','http:'].includes(url.protocol)&&!url.username&&!url.password?url.href:null}catch{return null}}
 selected(card){return this.batchSelection.get(card.id)!==false}
 batchGroups(){const groups={send_email:[],spend_money:[],approve_design:[],other:[]};for(const card of this.needs())groups[this.kind(card)||'other'].push(card);return groups}
 renderBatches(parent){this.heading(parent,'Stay in one kind of headspace','Review details, uncheck exceptions, then approve one kind at a time. Only recorded amounts can join spending.');
  parent.append(this.node('p','batch-review-note','Checked cards go to Ted for review. Exact emails and spending may still need a separate approval.'));
  const groups=this.batchGroups();let visible=0;
  for(const kind of ['send_email','spend_money','approve_design','other']){const cards=groups[kind];if(!cards.length)continue;visible++;
   const bundle=this.node('section','batch-bundle');bundle.dataset.batchKind=kind;const title=this.node('div','batch-title');title.append(this.node('h4',null,this.kindName(kind)),this.node('span',null,`${cards.length} ${cards.length===1?'row':'rows'}`));bundle.append(title);
   const list=this.node('div','batch-rows');for(const card of cards){const row=this.node('div','batch-row');const eligible=this.batchEligible(card);
    if(eligible){const label=this.node('label','batch-choice');const input=this.node('input');input.type='checkbox';input.checked=this.selected(card);input.setAttribute('aria-label',card.title);input.addEventListener('change',()=>{this.batchSelection.set(card.id,input.checked);this.redraw()});label.append(input,this.node('span',null,card.title));row.append(label)}
    else{row.classList.add('batch-held');row.append(this.node('span','batch-held-label',card.title),this.node('strong',null,'Held'))}
    if(card.body)row.append(this.node('p',null,card.body));
    const image=this.imageURL(card.image_url);if(kind==='approve_design'&&image){const link=this.node('a','batch-image');link.href=image;link.target='_blank';link.rel='noopener noreferrer';link.referrerPolicy='no-referrer';link.setAttribute('aria-label',`Open full image for ${card.title}`);const thumb=this.node('img');thumb.src=image;thumb.alt=`Preview of ${card.title}`;thumb.loading='lazy';thumb.referrerPolicy='no-referrer';link.append(thumb,this.node('span',null,'Open full image'));row.append(link)}
    if(kind==='spend_money'&&eligible)row.append(this.node('small','batch-amount',this.formatMoney(Number(card.amount_cents),card.currency)));
    if(!eligible)row.append(this.node('small','batch-reason',!this.kind(card)?'Decision kind is not recorded. Review this card individually.':kind==='spend_money'?'No positive recorded amount and currency for approval.':'This card needs a saved revision.'));
    list.append(row)}bundle.append(list);
   const selected=cards.filter(card=>this.batchEligible(card)&&this.selected(card));const foot=this.node('div','batch-footer');
   if(kind==='spend_money'){const totals=new Map();for(const card of selected)totals.set(card.currency,(totals.get(card.currency)||0)+Number(card.amount_cents));const copy=[...totals].map(([currency,cents])=>this.formatMoney(cents,currency)).join(' + ')||'No amount selected';foot.append(this.node('p','batch-total',`Selected total ${copy}`))}
   else foot.append(this.node('p','batch-total',`${selected.length} included, ${cards.length-selected.length} held`));
   if(selected.length){let label=`Approve ${selected.length} ${kind==='send_email'?(selected.length===1?'email':'emails'):kind==='approve_design'?(selected.length===1?'design':'designs'):(selected.length===1?'decision':'decisions')}`;
    if(kind==='spend_money'){const currencies=new Set(selected.map(c=>c.currency));if(currencies.size===1)label=`Approve ${this.formatMoney(selected.reduce((sum,c)=>sum+Number(c.amount_cents),0),selected[0].currency)}`}
    const approve=this.button(label,'primary',()=>this.approveBatch(kind,selected));approve.disabled=this.busy;foot.append(approve)}
   bundle.append(foot);parent.append(bundle)
  }
  if(!visible)this.empty(parent,'No decisions need batching right now.');
 }
 async approveBatch(kind,cards){if(this.busy||!cards.length)return;const selected=cards.filter(card=>this.needs().some(current=>current.id===card.id&&this.batchEligible(current)));
  if(!selected.length)return;this.busy=true;this.redraw();try{const data=await this.api('POST',{action:'batch_approve',kind,items:selected.map(card=>({id:card.id,revision:card.revision}))});
   if(!data.ok||!Array.isArray(data.approved))throw new Error('Batch approval was not confirmed. Refresh to check these cards.');
   for(const row of data.approved)this.batchSelection.delete(typeof row==='string'?row:row.id);this.notice(`${data.approved.length} ${data.approved.length===1?'decision':'decisions'} approved.`);await this.reloadCards();
  }catch(error){this.notice(error.message,true);await this.reloadCards()}finally{this.busy=false;this.redraw()}
 }
}
