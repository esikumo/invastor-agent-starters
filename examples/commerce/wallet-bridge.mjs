// Owner-configured local wallet only. stdout is a private machine-readable channel.
import {pathToFileURL} from "node:url";
import {isAbsolute} from "node:path";
const modulePath=process.argv[2];
if(!modulePath||!isAbsolute(modulePath))throw Error("Absolute trusted wallet module path required");
let input="";
for await(const part of process.stdin){input+=part;if(input.length>3000000)throw Error("Request too large");}
const {action,value}=JSON.parse(input);
if(!["prepare","broadcast"].includes(action))throw Error("Unsupported wallet action");
const {wallet}=await import(pathToFileURL(modulePath).href);
if(typeof wallet?.[action]!=="function")throw Error("Wallet adapter unavailable");
const result=await wallet[action](value);
process.stdout.write(JSON.stringify(result));
