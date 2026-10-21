'use strict';
/* Shared by the static UI and the server integration. It contains no account data. */
(()=>{
 const aliases={money:'money_out',money_out:'money_out',spend:'money_out',spending:'money_out',spend_money:'money_out',send:'your_words',sends:'your_words',email:'your_words',send_email:'your_words',your_words:'your_words',copy:'your_words',words:'your_words',db:'database_write',database:'database_write',sql:'database_write',db_write:'database_write',database_write:'database_write',legal:'legal',signature:'legal',signatures:'legal',login:'your_login',auth:'your_login',your_login:'your_login'};
 const normalize=value=>{const k=String(value||'').toLowerCase().trim().replace(/[\s-]+/g,'_');return aliases[k]||k;};
 const isReserved=value=>['money_out','your_words','database_write','legal','your_login'].includes(normalize(value));
 globalThis.TedDecisionKinds=Object.freeze({normalize,isReserved});
})();
