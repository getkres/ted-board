/** Server-only seam. The private handler verifies separate credentials before calling it. */
export type ReconciliationItem = {
 id:string; kind:'card'|'job'|'approval'|'pr'|'sql'|'mockup'; card_id:string|null;
 owner:string; next_action_due:string; action_started_at:string; status:'open'|'dead_letter';
 stage:string; priority:0|1|2; summary:string; expected_updated_at?:string;
};
export type Reconciliation = {generated_at:string;items:ReconciliationItem[];banner:boolean;ted_queue:string[];coverage_defects?:string[]};
export type CloseVerified = {card_id:string;expected_updated_at:string};
export type RouteTed = {card_id:string;expected_section:'needs_you';expected_updated_at:string;line:string};
export type ReconciliationStore = {read():Promise<Reconciliation|null>;publish(value:Reconciliation):Promise<Record<string,unknown>>;routeTed?(value:RouteTed):Promise<Record<string,unknown>>;closeVerified?(value:CloseVerified):Promise<Record<string,unknown>>};
type Request = {method:string;principal:'page'|'worker'|null;body?:unknown};
type Result = {status:number;body:Record<string,unknown>};
const idPattern=/^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$/;
const cardPattern=/^[A-Za-z0-9._-]{1,64}$/;
const ownerPattern=/^(?:ted|sebastian|external|worker:[A-Za-z0-9._:/-]{1,128})$/;
const itemFields=new Set(['id','kind','card_id','owner','next_action_due','action_started_at','status','stage','priority','summary','expected_updated_at']);
function object(value:unknown):Record<string,unknown> {
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error('Expected an object');
 return value as Record<string,unknown>;
}
function text(value:unknown,max:number):string {
 if(typeof value!=='string'||!value.trim()||value.length>max||/[\u0000-\u001f\u007f\u2014\u2028\u2029]/.test(value))throw Error('Invalid text');
 return value;
}
function timestamp(value:unknown):string {
 const raw=text(value,40);
 if(!/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(raw))throw Error('Invalid timestamp');
 const day=new Date(`${raw.slice(0,10)}T00:00:00Z`);
 if(!Number.isFinite(Date.parse(raw))||!Number.isFinite(day.getTime())||day.toISOString().slice(0,10)!==raw.slice(0,10))throw Error('Invalid timestamp');
 return raw;
}
export function validateReconciliationPublish(input:unknown,now=Date.now()):Reconciliation {
 const body=object(input),generated_at=timestamp(body.generated_at);
 if(Date.parse(generated_at)>now+300000)throw Error('Future generation');
 if(!Array.isArray(body.items)||body.items.length>2000||typeof body.banner!=='boolean'||!Array.isArray(body.ted_queue)||body.ted_queue.length>2000)throw Error('Invalid snapshot');
 const seen=new Set<string>(),cards=new Set<string>();
 const items=body.items.map(raw=>{
  const row=object(raw);
  if(Object.keys(row).some(key=>!itemFields.has(key)))throw Error('Unknown item field');
  const id=text(row.id,192),kind=row.kind as ReconciliationItem['kind'];
  if(!idPattern.test(id)||seen.has(id)||!['card','job','approval','pr','sql','mockup'].includes(kind))throw Error('Invalid item identity');
  seen.add(id);
  const card_id=row.card_id===null?null:text(row.card_id,64);
  if(card_id!==null&&!cardPattern.test(card_id))throw Error('Invalid card identity');
  const owner=text(row.owner,136),next_action_due=timestamp(row.next_action_due),action_started_at=timestamp(row.action_started_at);
  if(!ownerPattern.test(owner)||Date.parse(action_started_at)>Date.parse(generated_at))throw Error('Invalid owner or action start');
  if(row.status!=='open'&&row.status!=='dead_letter')throw Error('Only open entities are published');
  const stage=text(row.stage,80),summary=text(row.summary,500);
  if(!Number.isInteger(row.priority)||Number(row.priority)<0||Number(row.priority)>2)throw Error('Invalid priority');
  const expected_updated_at=row.expected_updated_at===undefined?undefined:timestamp(row.expected_updated_at);
  if(kind==='card'){
   if(!card_id||!expected_updated_at||cards.has(card_id))throw Error('Card metadata requires a unique guarded card');
   cards.add(card_id);
  }
  return {id,kind,card_id,owner,next_action_due,action_started_at,status:row.status,stage,priority:row.priority,summary,...(expected_updated_at?{expected_updated_at}:{})} as ReconciliationItem;
 });
 const queue=new Set<string>(),byId=new Map(items.map(row=>[row.id,row]));
 const ted_queue=body.ted_queue.map(raw=>{
  const id=text(raw,192);
  if(queue.has(id)||byId.get(id)?.owner!=='ted')throw Error('Queue must contain distinct Ted entities');
  queue.add(id);return id;
 });
 const coverage=new Set<string>();
 let coverage_defects:string[]|undefined;
 if(body.coverage_defects!==undefined){
  if(!Array.isArray(body.coverage_defects)||body.coverage_defects.length>500)throw Error('Invalid coverage');
  coverage_defects=body.coverage_defects.map(raw=>{const source=text(raw,192);if(!idPattern.test(source)||coverage.has(source))throw Error('Invalid coverage source');coverage.add(source);return source});
 }
 const result={generated_at,items,banner:body.banner,ted_queue,...(coverage_defects?{coverage_defects}:{})};
 if(new TextEncoder().encode(JSON.stringify(result)).length>1_500_000)throw Error('Snapshot too large');
 return result;
}
const missingSchema=(error:unknown)=>['42P01','42883','PGRST202','PGRST205'].includes(String((error as {code?:string})?.code));
export async function readReconciliation(store:ReconciliationStore):Promise<{reconciliation:Reconciliation|null;reconciliation_error?:string}> {
 let value:Reconciliation|null;
 try{value=await store.read()}
 catch(error){return {reconciliation:null,reconciliation_error:missingSchema(error)?'schema_unavailable':'service_unavailable'}}
 if(value===null)return {reconciliation:null,reconciliation_error:'not_published'};
 try{return {reconciliation:validateReconciliationPublish(value)}}
 catch{return {reconciliation:null,reconciliation_error:'invalid_snapshot'}}
}
export async function handleReconciliationAction(request:Request,store:ReconciliationStore,now=Date.now()):Promise<Result|null> {
 const body=request.body&&typeof request.body==='object'&&!Array.isArray(request.body)?request.body as Record<string,unknown>:{};
 if(request.method!=='POST'||!['reconcile_publish','reconcile_route_ted','reconcile_close_verified'].includes(String(body.action)))return null;
 if(request.principal!=='worker')return {status:403,body:{error:'Forbidden'}};
 let value:Reconciliation|RouteTed|CloseVerified;
 const route=body.action==='reconcile_route_ted',close=body.action==='reconcile_close_verified';
 try{
  if(close){
   const card_id=text(body.card_id,64),expected_updated_at=timestamp(body.expected_updated_at);
   if(!cardPattern.test(card_id))throw Error('Invalid close');
   value={card_id,expected_updated_at};
  }else if(route){
   const card_id=text(body.card_id,64),expected_updated_at=timestamp(body.expected_updated_at),line=text(body.line??'awaiting ted review',240);
   if(!cardPattern.test(card_id)||body.expected_section!=='needs_you')throw Error('Invalid route');
   value={card_id,expected_section:'needs_you',expected_updated_at,line};
  }else value=validateReconciliationPublish(body,now);
 }catch{return {status:400,body:{error:'Invalid reconciliation payload'}}}
 if(close&&!store.closeVerified)return {status:503,body:{error:'Verified closure is unavailable'}};
 if(route&&!store.routeTed)return {status:503,body:{error:'Reconciliation routing is unavailable'}};
 try{return {status:200,body:close?await store.closeVerified!(value as CloseVerified):route?await store.routeTed!(value as RouteTed):await store.publish(value as Reconciliation)}}
 catch(error){
  if(['40001','22023'].includes(String((error as {code?:string})?.code)))return {status:409,body:{error:'Reconciliation or card state changed. Refresh before publishing.'}};
  return {status:503,body:{error:missingSchema(error)?'Reconciliation schema is unavailable':'Reconciliation service is unavailable'}};
 }
}
type DatabaseResult={data:unknown;error:{code?:string;message?:string}|null};
export type SupabaseReconciliationClient={rpc(name:string,args?:Record<string,unknown>):PromiseLike<DatabaseResult>};
export function createSupabaseReconciliationStore(client:SupabaseReconciliationClient):ReconciliationStore {
 return {
  async read(){const {data,error}=await client.rpc('ted_board_reconciliation_read');if(error)throw error;return data as Reconciliation|null},
  async closeVerified(value){
   const {data,error}=await client.rpc('ted_board_reconcile_close_verified',{p_card_id:value.card_id,p_expected_updated_at:value.expected_updated_at});
   if(error)throw error;
   if(!data||typeof data!=='object'||Array.isArray(data)||(data as Record<string,unknown>).ok!==true)throw Error('Invalid close acknowledgement');
   return data as Record<string,unknown>;
  },
  async routeTed(value){
   const {data,error}=await client.rpc('ted_board_reconcile_route_ted',{p_card_id:value.card_id,p_expected_updated_at:value.expected_updated_at,p_expected_section:value.expected_section,p_line:value.line});
   if(error)throw error;
   if(!data||typeof data!=='object'||Array.isArray(data)||(data as Record<string,unknown>).ok!==true)throw Error('Invalid route acknowledgement');
   return data as Record<string,unknown>;
  },
  async publish(value){
   const {data,error}=await client.rpc('ted_board_reconcile_publish',{p_generated_at:value.generated_at,p_items:value.items,p_banner:value.banner,p_ted_queue:value.ted_queue,p_coverage_defects:value.coverage_defects??[]});
   if(error)throw error;
   if(!data||typeof data!=='object'||Array.isArray(data)||(data as Record<string,unknown>).ok!==true)throw Error('Invalid publish acknowledgement');
   return data as Record<string,unknown>;
  },
 };
}
