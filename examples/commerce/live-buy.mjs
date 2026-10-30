// Node 20+. No payment without explicit approval and a separately authorized wallet.
import {connect} from "invastor-commerce";
import {createFilePaymentJournal} from "invastor-commerce/payment-journal";
import {pathToFileURL} from "node:url";
const {readFile}=await import("node:fs/promises");
if(process.env.INVASTOR_APPROVE_LIVE_PURCHASE!=="yes")throw Error("Set INVASTOR_APPROVE_LIVE_PURCHASE=yes only after owner spending and wallet approval");
const draft=JSON.parse(await readFile(process.env.INVASTOR_DRAFT_FILE,"utf8"));
if(!process.env.INVASTOR_OPERATION_ID)throw Error("Use a durable business-event INVASTOR_OPERATION_ID");
const agent=await connect({apiUrl:process.env.INVASTOR_API_BASE,clientId:process.env.INVASTOR_CLIENT_ID});
try{
 const catalog=await agent.catalog({q:process.env.INVASTOR_SEARCH||"",limit:20});
 if(!catalog.items.some(item=>item.id===draft.listingId))throw Error("Requested listing is outside this catalog/grant");
 const {quote}=await agent.quote(draft);
 console.log(JSON.stringify(quote));
 if(!quote.prePurchase||quote.prePurchase.requiresSellerClarification)throw Error("Resolve missing seller terms/delivery information before buying");
 const {wallet}=await import(pathToFileURL(process.env.INVASTOR_WALLET_MODULE).href);
 const key="inv_"+(await import("node:crypto")).createHash("sha256").update(process.env.INVASTOR_OPERATION_ID).digest("hex").slice(0,60);
 const result=await agent.buy(draft,{idempotencyKey:key,paymentCurrency:"usdcsol",wallet,
  journal:createFilePaymentJournal({directory:process.env.INVASTOR_PAYMENT_JOURNAL})});
 console.log(JSON.stringify({purchase:result.purchase,settlementPending:result.settlementPending}));
 if(result.purchase?.state==="PAID")console.log(JSON.stringify(await agent.watchPurchase({purchaseId:result.purchase.id})));
}finally{await agent.close();}
