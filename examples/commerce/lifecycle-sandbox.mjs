// Node 20+. Real sandbox API; no account, wallet or live financial endpoints.
if(!process.argv.includes("--approve-simulation"))throw Error("Pass --approve-simulation to permit fixture-only lifecycle actions");

const configuredBase=process.env.INVASTOR_API_BASE;
if(!configuredBase)throw Error("Set INVASTOR_API_BASE to your serving host plus /api");
const apiBase=new URL(configuredBase.replace(/\/+$/,"")+"/");
if(!["http:","https:"].includes(apiBase.protocol)||apiBase.username||apiBase.password||apiBase.search||apiBase.hash)
 throw Error("INVASTOR_API_BASE must be an HTTP(S) API URL without credentials, query or fragment");
const base=new URL("commerce/sandbox/",apiBase).href;
async function api(path,token,body,method=body===undefined?"GET":"POST"){
 for(let attempt=0;attempt<3;attempt++){
  let response;
  try{
   response=await fetch(base+path,{method,
    headers:{"Content-Type":"application/json","Accept":"application/json","User-Agent":"InVastor-Lifecycle-Sandbox/1.0",...(token?{Authorization:"Bearer "+token}:{})},
    body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(30000)});
  }catch{
   throw Object.assign(Error("Sandbox connection failed or timed out. No automatic write retry; reconcile the original purchase key before repeating a purchase."),{code:"SANDBOX_CONNECTION_FAILED",outcomeUnknown:method!=="GET"});
  }
  let value;
  try{value=JSON.parse(await response.text());}catch{}
  const object=value&&typeof value==="object"&&!Array.isArray(value);
  const rejected=response.status===429&&object&&value.sandbox===true&&value.code==="RATE_LIMITED";
  const safe=method==="GET"||rejected;
  if(attempt<2&&safe&&(response.status===429||[502,503,504].includes(response.status))){
   const header=response.headers.get("Retry-After");
   const seconds=header===null?(response.status===429?61:2):
    /^\d+$/.test(header)?Number(header):Math.ceil((Date.parse(header)-Date.now())/1000);
   if(Number.isFinite(seconds)&&seconds>=0&&seconds<=120){
    console.error("Sandbox temporarily unavailable (HTTP "+response.status+"); waiting "+Math.max(1,seconds)+" seconds before a safe retry.");
    await new Promise(r=>setTimeout(r,Math.max(1,seconds)*1000));continue;
   }
  }
  if(!object)throw Object.assign(Error("Sandbox returned a non-JSON response (HTTP "+response.status+"). Check the API URL or gateway. No automatic write retry; preserve the original purchase key."),{code:"SANDBOX_INVALID_RESPONSE",status:response.status,outcomeUnknown:method!=="GET"});
  if(!response.ok)throw Object.assign(Error(typeof value.error==="string"?value.error:"Sandbox request failed (HTTP "+response.status+")"),value,{status:response.status});
  return value;
 }
}

const assert=(value,message)=>{if(!value)throw Error(message);};
const expected={out_of_stock:"OUT_OF_STOCK",price_changed:"PRICE_CHANGED",budget_limit:"BUDGET_EXCEEDED",
 revoked_permission:"PERMISSION_REVOKED",insufficient_funds:"INSUFFICIENT_FUNDS",expired_permission:"PERMISSION_EXPIRED"};
const {scenarios}=await api("scenarios");
for(const [index,scenario] of scenarios.entries()){
 if(index===10){console.error("Respecting sandbox session-creation rate limit (61 seconds)");await new Promise(r=>setTimeout(r,61000));}
 const {token}=await api("sessions",null,{scenario});
 const key="lifecycle_"+crypto.randomUUID().replaceAll("-","");
 try{
  const {items}=await api("catalog",token);
  const quote=(await api("quotes",token,{listingId:items[0].id})).quote;
  if(scenario==="revoked_permission"){
    await api("session",token,undefined,"DELETE");
  }
  let prepared;
  try{prepared=await api("purchases",token,{quoteId:quote.id,idempotencyKey:key});}
  catch(e){if(e.code!=="OUTCOME_UNKNOWN")throw e;prepared=await api("purchases/by-key/"+key,token);}
  assert(!expected[scenario],"Expected scenario rejection");
  const path="purchases/"+prepared.purchase.id;
  const action=name=>api(path+"/actions",token,{action:name,confirmed:true});
  if(scenario==="duplicate_request"){
   const replay=await api("purchases",token,{quoteId:quote.id,idempotencyKey:key});
   assert(replay.purchase.id===prepared.purchase.id,"Duplicate order created");
  }
  await api(path+"/approve",token,{approved:true});
  await api(path+"/approve",token,{approved:true});
  assert((await api("session",token)).spentUsdCents===quote.totalUsdCents,"Payment debited twice");
  if(scenario==="refund"){
   const requested=await action("request_refund");
   assert(requested.purchase.lifecycle.refund.state==="REQUESTED","Refund request was not recorded");
   await action("complete_refund");await action("complete_refund");
   const state=await api("session",token);
   assert(state.simulatedBalanceUsdCents===10000&&state.spentUsdCents===quote.totalUsdCents,"Refund replay or spending authority changed");
  }else{
   try{await action("payout");throw Error("Payout before acceptance succeeded");}
   catch(e){if(e.code!=="PAYOUT_BLOCKED")throw e;}
   await action("submit_work");await action("accept_delivery");
   if(scenario==="payout_failure"){
    try{await action("payout");throw Error("Expected payout failure");}
    catch(e){if(e.code!=="PAYOUT_FAILED")throw e;assert(e.recovery?.mayCreateReplacementPayment===false,"Unsafe recovery");}
    assert((await api(path,token)).purchase.lifecycle.nextAction==="CONTACT_SUPPORT","Payout failure not retained");
   }else{
    await action("payout");await action("payout");
    assert((await api(path,token)).purchase.lifecycle.nextAction==="COMPLETE","Lifecycle did not complete");
   }
  }
  assert((await api("session",token)).purchaseCount===1,"Original purchase identity lost");
  console.log("PASS",scenario);
 }catch(e){
   if(!expected[scenario]||expected[scenario]!==e.code)throw e;
  console.log("PASS",scenario,e.code);
 }
}
// A dispute must block both acceptance and payout on a funded order.
{
 const {token}=await api("sessions",null,{scenario:"happy_path"});
 const {quote}=await api("quotes",token,{listingId:"sandbox-keyboard"});
 const {purchase}=await api("purchases",token,{quoteId:quote.id,idempotencyKey:"dispute_"+crypto.randomUUID().replaceAll("-","")});
 const path="purchases/"+purchase.id;
 await api(path+"/approve",token,{approved:true});
 await api(path+"/actions",token,{action:"submit_work",confirmed:true});
 await api(path+"/actions",token,{action:"dispute",confirmed:true});
 try{await api(path+"/actions",token,{action:"payout",confirmed:true});throw Error("Disputed payout allowed");}
 catch(e){if(e.code!=="PAYOUT_BLOCKED")throw e;}
 assert((await api(path,token)).purchase.lifecycle.nextAction==="REVIEW_DISPUTE","Dispute not visible");
 console.log("PASS disputed_order");
}
