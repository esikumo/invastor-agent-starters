// Read-only live order monitor. Node 20+, installed serving-release SDK.
import { connect } from "invastor-commerce";
const apiUrl=process.env.INVASTOR_API_BASE;
const clientId=process.env.INVASTOR_CLIENT_ID;
const id=process.env.PURCHASE_ID;
const key=process.env.PURCHASE_KEY;
if(!apiUrl || !clientId || (!!id === !!key))throw Error("Set INVASTOR_API_BASE, original INVASTOR_CLIENT_ID and exactly one original PURCHASE_ID or PURCHASE_KEY");
const agent=await connect({apiUrl,clientId});
try {
 const result=await agent.watchPurchase({
  ...(id?{purchaseId:Number(id)}:{idempotencyKey:key}),
  timeoutMs:120000,
  onUpdate:({purchase})=>console.log(JSON.stringify({id:purchase.id,lifecycle:purchase.lifecycle}))
 });
 console.log(JSON.stringify({monitoring:result.monitoring}));
 if(result.purchase?.id)console.log(JSON.stringify(await agent.evidence(result.purchase.id)));
 if(result.monitoring.outcome!=="COMPLETE")process.exitCode=2;
} finally {await agent.close();}
