import '../decision-kinds.js';
const decisionKinds=(globalThis as unknown as {TedDecisionKinds:{isReserved:(value:unknown)=>boolean}}).TedDecisionKinds;
/** Server-only integration seam. Authenticate in the existing handler first. */
export type SnapshotKind = 'decisions' | 'routines' | 'pods' | 'roadmap';
export type Json = null | boolean | number | string | Json[] | {[key:string]:Json};
export interface Snapshot {kind:SnapshotKind; key:string; payload:Record<string,Json>; generated_at:string}
export interface ReviewChoice {item_id:string; choice:'keep'|'skip'|'card'; operation_id:string}
export interface SnapshotStore {read():Promise<Snapshot[]>; push(rows:Snapshot[]):Promise<void>}
export type Principal = 'page' | 'worker' | null;
export interface ActionRequest {method:string; resource?:string; scope?:string; body?:unknown; principal:Principal}
export interface ActionResult {status:number; body:Record<string,unknown>}
// Durable hook must check item existence, write a receipt, and deduplicate operation_id atomically.
export type ReviewHook = (choice:ReviewChoice)=>Promise<{ok:true; item_id:string; choice:string}>;

function record(value:unknown):Record<string,unknown> {
  if (!value || typeof value!=='object' || Array.isArray(value)) throw Error('Expected an object');
  return value as Record<string,unknown>;
}
function text(value:unknown,max=200):string {
  if(typeof value!=='string'||!value.trim()||value.length>max||/[\u0000-\u001f]/.test(value)) throw Error('Invalid text');
  return value;
}
function cleanJson(value:unknown,depth=0):void {
  if(depth>20) throw Error('Payload nesting exceeds limit');
  if(value===null||typeof value==='boolean') return;
  if(typeof value==='number'&&Number.isFinite(value)) return;
  if(typeof value==='string') {
    if(value.length>50000) throw Error('Text exceeds limit');
    return;
  }
  if(Array.isArray(value)) {if(value.length>2000)throw Error('Too many rows');for(const item of value)cleanJson(item,depth+1);return}
  const object=record(value);
  for(const [key,item] of Object.entries(object)) {
    if(/^(?:__proto__|constructor|prototype|api[_-]?key|service[_-]?role|worker[_-]?key|page[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization|private[_-]?key)$/i.test(key)) throw Error('Sensitive field is not allowed');
    cleanJson(item,depth+1);
  }
}
function rows(payload:Record<string,unknown>,name:string,required=false):Record<string,unknown>[] {
  if(!(name in payload)&&!required)return [];
  const list=payload[name];
  if(!Array.isArray(list)||list.length>2000)throw Error('Invalid feed rows');
  return list.map(record);
}
export function validateSnapshotPush(input:unknown,now=Date.now()):Snapshot[] {
  const inputRows=record(input).snapshots;
  if(!Array.isArray(inputRows)||!inputRows.length||inputRows.length>50)throw Error('Expected 1 to 50 snapshots');
  const seen=new Set<string>();
  let total=0;
  return inputRows.map(value=>{
    const row=record(value),kind=row.kind as SnapshotKind;
    if(!['decisions','routines','pods','roadmap'].includes(kind))throw Error('Unknown snapshot kind');
    const key=text(row.key,100);
    if(!/^[a-zA-Z0-9][a-zA-Z0-9_./:-]*$/.test(key))throw Error('Invalid snapshot key');
    if(seen.has(kind+':'+key))throw Error('Duplicate snapshot key');
    seen.add(kind+':'+key);
    const date=text(row.generated_at,40),time=Date.parse(date);
    if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})$/.test(date)||!Number.isFinite(time)||time>now+300000)throw Error('Invalid generated_at');
    const payload=record(row.payload);
    cleanJson(payload);
    const bytes=new TextEncoder().encode(JSON.stringify(payload)).length;
    total+=bytes;
    if(bytes>262144||total>1048576)throw Error('Payload exceeds limit');
    if(kind==='decisions') {
      const decisions=rows(payload,'items' in payload?'items':'decisions',true);rows(payload,'woke');
      for(const decision of decisions) {
        text(decision.id);
        if(!['done','proposed','approve'].includes(String(decision.status)))throw Error('Invalid decision status');
        if((decisionKinds.isReserved(decision.decision_kind)||decisionKinds.isReserved(decision.kind))&&decision.status!=='approve')throw Error('Reserved decision requires approval');
        if(decision.veto_hours!==undefined&&(!Number.isFinite(decision.veto_hours)||Number(decision.veto_hours)<0||Number(decision.veto_hours)>168))throw Error('Invalid veto hours');
      }
    } else if(kind==='routines') {rows(payload,'items' in payload?'items':'routines',true);for(const item of rows(payload,'review_items'))text(item.id)}
    else if(kind==='pods') rows(payload,'items' in payload?'items':'pods',true);
    else if('items' in payload) rows(payload,'items',true);
    else {for(const column of ['now','next','later','shipped'])rows(payload,column,true)}
    return {kind,key,payload:payload as Record<string,Json>,generated_at:new Date(time).toISOString()};
  });
}
export function validateReviewChoice(input:unknown):ReviewChoice {
  const row=record(input),item_id=text(row.item_id),operation_id=text(row.operation_id,36);
  if(!['keep','skip','card'].includes(String(row.choice)))throw Error('Invalid review choice');
  if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(operation_id))throw Error('Invalid operation ID');
  return {item_id,choice:row.choice as ReviewChoice['choice'],operation_id};
}
const missingSchema=(error:unknown)=>['42P01','42883','PGRST202','PGRST205'].includes(String((error as {code?:string})?.code));
export async function handleSnapshotAction(request:ActionRequest,store:SnapshotStore,reviewChoice?:ReviewHook):Promise<ActionResult|null> {
  const body=request.body&&typeof request.body==='object'&&!Array.isArray(request.body)?request.body as Record<string,unknown>:{};
  const isRead=request.method==='GET'&&(request.resource==='snapshots'||request.scope==='snapshots');
  const isPush=request.method==='POST'&&body.action==='snapshot_push';
  const isReview=request.method==='POST'&&body.action==='review_choice';
  if(!isRead&&!isPush&&!isReview)return null; // Let the existing handler continue.
  if(!request.principal)return {status:401,body:{error:'Unauthorized'}};
  if((isPush&&request.principal!=='worker')||(isReview&&request.principal!=='page'))return {status:403,body:{error:'Forbidden'}};
  if(isReview&&!reviewChoice)return {status:501,body:{error:'Review choices are not configured'}};
  let validated:Snapshot[]|ReviewChoice|undefined;
  try {if(isPush)validated=validateSnapshotPush(body);if(isReview)validated=validateReviewChoice(body)}
  catch {return {status:400,body:{error:'Invalid snapshot or review payload'}}}
  try {
    if(isRead)return {status:200,body:{snapshots:await store.read(),capabilities:{snapshots:true,review_choice:Boolean(reviewChoice)}}};
    if(isPush){await store.push(validated as Snapshot[]);return {status:200,body:{ok:true}}}
    return {status:200,body:await reviewChoice!(validated as ReviewChoice)};
  } catch(error) {
    if(missingSchema(error))return isRead?{status:200,body:{snapshots:[],capabilities:{snapshots:false,review_choice:false}}}:{status:503,body:{error:'Snapshot schema is not available'}};
    return {status:503,body:{error:'Snapshot service is temporarily unavailable'}};
  }
}

// Structural interface avoids publishing private handler imports or adding an SDK dependency.
type DatabaseResult<T>={data:T|null;error:{code?:string;message?:string}|null};
type SnapshotQuery={order(column:string):SnapshotQuery;range(from:number,to:number):PromiseLike<DatabaseResult<Snapshot[]>>};
export interface SupabaseSnapshotClient {
  from(table:'ted_board_snapshots'):{select(columns:string):SnapshotQuery};
  rpc(name:'ted_board_snapshot_push',args:{p_rows:Snapshot[]}):PromiseLike<DatabaseResult<unknown>>;
}
export function createSupabaseSnapshotStore(client:SupabaseSnapshotClient):SnapshotStore {
  return {
    async read() {
      const all:Snapshot[]=[];
      for(let offset=0;offset<1000;offset+=100) {
        const {data,error}=await client.from('ted_board_snapshots').select('kind,key,payload,generated_at').order('kind').order('key').range(offset,offset+99);
        if(error)throw error;
        const found=data||[];all.push(...found);
        if(found.length<100)return all;
      }
      throw Error('Snapshot row limit reached'); // Never silently truncate feeds.
    },
    async push(values) {
      const {error}=await client.rpc('ted_board_snapshot_push',{p_rows:values});
      if(error)throw error;
    },
  };
}
