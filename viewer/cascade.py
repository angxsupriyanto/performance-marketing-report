"""Browser code shared by the Performa sidebar and the Budget picker: Channel narrows Source, Source narrows Medium, and the three narrow Campaign.

Each option is an element with data-key (channel, source, medium or campaign) and data-label, holding one checkbox. `rel` is performance.relations().
Parents only restrict what is below them. A ticked value that no longer fits is unticked and counted. A campaign the snapshot knows nothing about
(a name only the newest report has) is shown only while no parent is ticked."""
import json

CASCADE_JS = r"""
function makeCascade(rel){
  var idx={};['channel','source','medium','campaign'].forEach(function(k){idx[k]={};rel.labels[k].forEach(function(l,i){idx[k][l]=i;});});
  var LEVELS=['source','medium','campaign'],UP={source:['channel'],medium:['channel','source'],campaign:['channel','source','medium']},TITLE={channel:'Channel',source:'Source',medium:'Medium'};
  function avail(c){
    var pick={};['channel','source','medium'].forEach(function(k){var s=null;(c[k]||[]).forEach(function(l){if(l in idx[k]){s=s||{};s[idx[k][l]]=1;}});pick[k]=s;});
    var rows=rel.combos.filter(function(r){return !pick.channel||pick.channel[r[0]];}),out={source:{},medium:{},campaign:{}};
    rows.forEach(function(r){out.source[rel.labels.source[r[1]]]=1;});
    rows=rows.filter(function(r){return !pick.source||pick.source[r[1]];});
    rows.forEach(function(r){out.medium[rel.labels.medium[r[2]]]=1;});
    rows=rows.filter(function(r){return !pick.medium||pick.medium[r[2]];});
    rows.forEach(function(r){out.campaign[rel.labels.campaign[r[3]]]=1;});
    return out;
  }
  return function apply(opts){
    function chosen(){var c={channel:[],source:[],medium:[],campaign:[]};opts.forEach(function(o){if(o.querySelector('input').checked)c[o.dataset.key].push(o.dataset.label);});return c;}
    var dropped=0;
    LEVELS.forEach(function(k){var a=avail(chosen());opts.forEach(function(o){var i=o.querySelector('input');if(o.dataset.key===k&&i.checked&&!a[k][o.dataset.label]){i.checked=false;dropped++;}});});
    var c=chosen(),a=avail(c),parents=c.channel.length+c.source.length+c.medium.length>0;
    opts.forEach(function(o){var k=o.dataset.key;o.dataset.cut=(k==='channel'||!parents||a[k][o.dataset.label])?'':'1';});
    var hints={};LEVELS.forEach(function(k){var up=UP[k].filter(function(u){return c[u].length;}).map(function(u){return TITLE[u];});hints[k]=up.length?'Disaring oleh '+up.join(', ')+' yang dipilih.':'';});
    return {dropped:dropped,chosen:c,parents:parents,hints:hints};
  };
}
"""


def rel_json(rel: dict) -> str:
    """The relations as JSON that is safe inside a script element (no closing tag, no U+2028 surprises)."""
    return json.dumps(rel, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
