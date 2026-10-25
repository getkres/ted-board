/** Server-only seam for the existing, authenticated ted-mockups Edge Function. */
export type ArchiveScope = {project:string; batch?:string; mockup_id?:string};
type Row = {id:string; status:string; verdict?:string|null};
export interface ArchiveStore {setArchived(scope:ArchiveScope, archived:boolean):Promise<Row[]>}
type Result = {status:number; body:Record<string,unknown>};

export async function handleMockupArchive(body:Record<string,unknown>, principal:'page'|'worker'|null, store:ArchiveStore):Promise<Result|null> {
 if(!['archive','unarchive'].includes(String(body.action)))return null;
 if(principal!=='page')return {status:403,body:{error:'forbidden'}};
 const frame=body.mockup_id!==undefined;
 const allowed=new Set(['key','action','project',frame?'mockup_id':'batch']);
 if(Object.keys(body).some(k=>!allowed.has(k))||typeof body.project!=='string'||!body.project.trim()||body.project.length>100||
   (frame?typeof body.mockup_id!=='string'||!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(body.mockup_id):
    typeof body.batch!=='string'||!body.batch.trim()||body.batch.length>200)){
  return {status:400,body:{error:'Use an exact project and either a batch or a frame id.'}};
 }
 const scope:ArchiveScope={project:body.project,...(frame?{mockup_id:body.mockup_id as string}:{batch:body.batch as string})};
 try{return {status:200,body:{ok:true,mockups:await store.setArchived(scope,body.action==='archive')}};}
 catch{return {status:503,body:{error:'Could not save the archive change. Refresh to check it, and try again.'}};}
}

// Supply only the service-role client already owned by the private handler.
export function createMockupArchiveStore(db:{from:(table:string)=>any}):ArchiveStore {
 const read=async(query:()=>any)=>{
  const rows:any[]=[];
  for(let start=0;start<100000;start+=1000){
   const {data,error}=await query().order('id').range(start,start+999);
   if(error||!Array.isArray(data))throw Error('Read failed');
   rows.push(...data);if(data.length<1000)return rows;
  }
  throw Error('Too many rows');
 };
 const scoped=(q:any,s:ArchiveScope)=>s.mockup_id?q.eq('project',s.project).eq('id',s.mockup_id):q.eq('project',s.project).eq('batch',s.batch);
 return {async setArchived(scope,archived){
  const rows:Row[]=await read(()=>scoped(db.from('ted_mockups').select('id,status,verdict'),scope));
  const targets=rows.filter(row=>archived?row.status!=='archived':row.status==='archived');
  const legacy=new Set<string>();
  if(!archived){
   const ids=targets.filter(row=>!row.verdict).map(row=>row.id);
   for(let i=0;i<ids.length;i+=500){
    const receipts=await read(()=>db.from('ted_decisions').select('id,item_id').eq('page','mockups').eq('choice','pick').in('item_id',ids.slice(i,i+500)));
    receipts.forEach(r=>legacy.add(r.item_id));
   }
  }
  const result:Row[]=rows.filter(row=>!targets.includes(row));
  for(const status of archived?['archived']:['open','picked']){
   const ids=targets.filter(row=>archived||(row.verdict==='approved'||!row.verdict&&legacy.has(row.id)?'picked':'open')===status).map(row=>row.id);
   for(let i=0;i<ids.length;i+=500){
    let query=scoped(db.from('ted_mockups').update({status}),scope).in('id',ids.slice(i,i+500));
    // A restore must never overwrite a frame that another action already restored.
    if(!archived)query=query.eq('status','archived');
    const {data,error}=await query.select('id,status,verdict');
    if(error||!Array.isArray(data))throw Error('Write failed');result.push(...data);
   }
  }
  return result;
 }};
}
