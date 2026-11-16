"""Refresh presentation figures from frozen evidence and capture the current UI."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent

FIGURES = r"""async (e) => {
  const ink='#f5f2e9', muted='#b2c5ce', teal='#66e1cc', salmon='#ff9375', grid='#28404c';
  const axis={gridcolor:grid,zerolinecolor:'#6b818b',tickfont:{size:13,color:muted},automargin:true};
  const base={width:735,height:320,paper_bgcolor:'#081822',plot_bgcolor:'#081822',
    font:{family:'Arial',size:14,color:ink},margin:{l:65,r:20,t:15,b:45},
    xaxis:{...axis},yaxis:{...axis},showlegend:false};
  const exportPlot=async (traces,extra={}) => {
    await Plotly.newPlot('figure',traces,{...base,...extra},{staticPlot:true});
    return Plotly.toImage('figure',{format:'svg',width:735,height:320});
  };
  const a=e.analyses.air_europe.response,s=a.series,r=a.result;
  const x=s.dates.map(d=>d+'-15');
  const low=s.t.map((v,i)=>Math.min(s.fit[i]+(r.ci_low-r.slope)/10*(v-s.t_mean),s.fit[i]+(r.ci_high-r.slope)/10*(v-s.t_mean)));
  const high=s.t.map((v,i)=>Math.max(s.fit[i]+(r.ci_low-r.slope)/10*(v-s.t_mean),s.fit[i]+(r.ci_high-r.slope)/10*(v-s.t_mean)));
  const air=await exportPlot([
    {x,y:s.anomaly,type:'scatter',mode:'lines',line:{color:'#78929d',width:.7},opacity:.55},
    {x,y:low,type:'scatter',mode:'lines',line:{width:0}},
    {x,y:high,type:'scatter',mode:'lines',line:{width:0},fill:'tonexty',fillcolor:'rgba(102,225,204,.16)'},
    {x,y:s.running12,type:'scatter',mode:'lines',line:{color:ink,width:1.6}},
    {x,y:s.fit,type:'scatter',mode:'lines',line:{color:teal,width:3}}
  ],{xaxis:{...axis,type:'date',dtick:'M120'},yaxis:{...axis,title:{text:'Temperature anomaly (°C)',font:{size:13}}}});
  const b=e.simulation_batch.response,pct=[100*b.naive_significant/b.runs,100*b.corrected_significant/b.runs,5];
  const bounds=[b.naive_interval,b.corrected_interval];
  const batch=await exportPlot([{type:'bar',x:['Naive test','Memory-aware test','5% reference'],y:pct,
    marker:{color:[salmon,teal,'#7f919b']},text:pct.map(v=>v.toFixed(1)+'%'),textposition:'outside',cliponaxis:false,
    error_y:{type:'data',symmetric:false,array:bounds.map((v,i)=>100*v[1]-pct[i]).concat(0),
      arrayminus:bounds.map((v,i)=>pct[i]-100*v[0]).concat(0),color:ink,thickness:1.5,width:7}}],
    {margin:{l:65,r:20,t:36,b:45},yaxis:{...axis,title:{text:'False alarms (%)',font:{size:13}},range:[0,60]},bargap:.48});
  const seasonal=[e.analyses.ndvi_annual.response.result,e.analyses.ndvi_summer.response.result];
  const season=await exportPlot([{type:'scatter',mode:'markers',x:seasonal.map(v=>v.slope),y:[1,0],
    marker:{color:[teal,salmon],size:12},error_x:{type:'data',symmetric:false,color:ink,thickness:2,width:7,
      array:seasonal.map(v=>v.ci_high-v.slope),arrayminus:seasonal.map(v=>v.slope-v.ci_low)}}],
    {margin:{l:115,r:30,t:35,b:60},xaxis:{...axis,title:{text:'NDVI change per decade',font:{size:14}},zerolinewidth:2},
     yaxis:{...axis,tickvals:[1,0],ticktext:['All months','Jun–Aug'],range:[-.6,1.6],gridcolor:'#081822'}});
  const sp=e.simulation_spikes.response, dates=sp.original.dates.map(d=>d+'-15');
  const spikes=await exportPlot([
    {type:'scatter',mode:'lines',x:dates,y:sp.values,line:{color:'#8ba3ad',width:1.1}},
    {type:'scatter',mode:'lines',x:dates,y:sp.fit,line:{color:salmon,width:3}},
    {type:'scatter',mode:'lines',x:dates,y:sp.original.fit,line:{color:teal,width:3,dash:'dash'}},
    {type:'scatter',mode:'markers',x:sp.spikes.map(i=>dates[i]),y:sp.spikes.map(i=>sp.values[i]),marker:{color:salmon,size:10,symbol:'diamond'}}
  ],{xaxis:{...axis,type:'date',dtick:'M12'},yaxis:{...axis,title:{text:'Synthetic units',font:{size:13}}}});
  return {air,batch,season,spikes};
}"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8776")
    parser.add_argument("--project-root", type=Path, required=True,
                        help="Separate application checkout supplying the vendored Plotly library.")
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    evidence = json.loads((HERE / "evidence.json").read_text())
    assets = HERE / "assets"
    record = {"captured_at": datetime.now(ZoneInfo("Europe/Warsaw")).isoformat(timespec="seconds"),
              "base_url": args.base_url, "evidence_sha256": hashlib.sha256((HERE / "evidence.json").read_bytes()).hexdigest(),
              "browser_errors": [], "checks": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True,
                                   args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, color_scheme="dark",
                                      reduced_motion="reduce", ignore_https_errors=True)
        page = context.new_page()
        page.set_default_timeout(90000)
        page.on("pageerror", lambda error: record["browser_errors"].append(str(error)))
        page.set_content('<div id="figure"></div>')
        page.add_script_tag(path=str(project_root / "web/vendor/plotly.min.js"))
        for name, url in page.evaluate(FIGURES, evidence).items():
            (assets / f"{name}.svg").write_text(unquote(url.split(",", 1)[1]))
        print("Refreshed four scientific figures from frozen evidence.", flush=True)
        page.goto(args.base_url + "/?lang=en#view=atlas&var=t2m&region=central_europe&start=1981&end=2025", wait_until="domcontentloaded")
        page.wait_for_function("lastAnalysis && lastAnalysis.result && document.querySelector('#chart').data")
        page.evaluate("document.fonts.ready")
        actual = page.evaluate("lastAnalysis.result")
        assert actual == evidence["analyses"]["air_europe"]["response"]["result"]
        record["checks"]["detective_matches_recorded_result"] = True
        page.locator("#atlas .grid").screenshot(path=str(assets / "detective-ui.png"))
        page.locator("#matrix").screenshot(path=str(assets / "matrix-ui.png"))
        print("Captured Detective and period matrix.", flush=True)
        page.locator("#tab-lab").click()
        page.wait_for_function("spikeExample && document.querySelector('#simSpikeChart').data")
        assert page.evaluate("spikeExample") == evidence["simulation_spikes"]["response"]
        record["checks"]["outlier_exercise_matches_current_ui"] = True
        page.locator("#simMany").click()
        page.wait_for_function("lastSimulationBatch && document.querySelector('#simMulti').data")
        assert page.evaluate("lastSimulationBatch") == evidence["simulation_batch"]["response"]
        page.locator("#lab .grid2").screenshot(path=str(assets / "lab-ui.png"))
        page.locator("#tab-resilience").click()
        page.wait_for_selector("#resilience .resilience-cards > article")
        page.wait_for_function("!document.querySelector('#resilience').innerText.includes('Loading')")
        page.locator("#resilience").screenshot(path=str(assets / "resilience-ui.png"))
        record["checks"]["resilience_tab_available_locally"] = True
        print("Captured laboratory and Resilience.", flush=True)
        page.locator("#tab-globe").click()
        page.wait_for_function("typeof G !== 'undefined' && G.map && G.map.isStyleLoaded()")
        page.locator("#gVar").select_option("gistemp")
        page.wait_for_function("G.var === 'gistemp' && G.grids.length > 0")
        page.evaluate("G.spin=false; G.map.jumpTo({center:[15,20],zoom:1.3});")
        page.wait_for_timeout(2500)
        # Preserve the high-resolution LST cover; refresh it separately with capture_cover.py.
        page.locator("#gVar").select_option("t2m")
        page.locator("#gRegions [data-r='central_europe']").click()
        page.wait_for_function("G.var === 't2m' && G.grids.some(g=>g.region==='central_europe')")
        page.evaluate("G.map.jumpTo({center:[19,52],zoom:2}); setSelection([14,49,24,55],true);")
        page.locator("#gModel").select_option("t2m")
        a = evidence["analyses"]["air_europe"]["response"]
        page.evaluate("a => showResult(I18N.response('analysis',a),'central_europe')", a)
        page.wait_for_function("document.querySelector('#gChart').data")
        page.wait_for_timeout(1000)
        page.locator("#globe").screenshot(path=str(assets / "selection-ui.png"))
        record["checks"]["selection_reused_recorded_existing_region"] = True
        browser.close()
    record["assets_sha256"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in sorted(assets.iterdir()) if path.name != "step.svg"}
    (HERE / "capture-validation.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(record["checks"]), flush=True)


if __name__ == "__main__":
    main()
