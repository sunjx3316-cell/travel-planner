import {plan} from './router.js';
let network;
self.onmessage=async({data})=>{
  try {
    if(data.type==='init'){
      const response=await fetch('./data/network.json');
      if(!response.ok)throw new Error('时刻表下载失败，请刷新重试。');
      network=await response.json();
      self.postMessage({type:'ready',network});
    }else if(data.type==='plan'){
      const start=performance.now();
      const result=plan(network,data.options);
      self.postMessage({type:'result',id:data.id,result,elapsed:performance.now()-start});
    }
  }catch(error){self.postMessage({type:'error',id:data.id,error:error.message});}
};
