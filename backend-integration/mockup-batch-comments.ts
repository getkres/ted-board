/** Server-only seam, invoked before the private legacy pin branch. No DB client or secrets. */
type Input={mockup_id:string;text:string};
// post must use the existing private pin/receipt transaction. See README.md.
export interface BatchNoteStore {post(input:Input):Promise<unknown>}
type Result={status:number;body:Record<string,unknown>};
const uuid=(v:unknown)=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
export async function handleMockupBatchNote(body:Record<string,unknown>,principal:'page'|'worker'|null,store:BatchNoteStore):Promise<Result|null>{
 if(body.action!=='pin'||!Object.hasOwn(body,'batch_note'))return null;
 if(principal!=='page')return {status:403,body:{error:'forbidden'}};
 const allowed=new Set(['key','action','mockup_id','batch_note','text']);
 if(body.batch_note!==true||!uuid(body.mockup_id)||typeof body.text!=='string'||!body.text.trim()||body.text.length>1200||Object.keys(body).some(k=>!allowed.has(k)))return {status:400,body:{error:'Use one mockup anchor and a batch comment of 1 to 1200 characters.'}};
 const input={mockup_id:body.mockup_id as string,text:body.text.trim()};
 try{
  const result:any=await store.post(input),pin=result?.pin;
  if(!pin||!uuid(pin.id)||pin.mockup_id!==input.mockup_id||pin.batch_note!==true||!Number.isSafeInteger(result.decision_id)||result.decision_id<1||!Array.isArray(pin.thread)||!pin.thread.some((m:any)=>m?.who==='seb'&&m.text===input.text))throw Error('Unconfirmed receipt');
  return {status:200,body:{ok:true,pin,decision_id:result.decision_id}};
 }catch{return {status:503,body:{error:'Comment was not confirmed. Refresh before sending again. Your draft is kept.'}};}
}
