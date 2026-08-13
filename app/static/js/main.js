(function(){

  var DATA = {
    cities: {
      lagos:        { label:"Lagos",         code:"LOS", rentFactor:1.00 },
      abuja:        { label:"Abuja",         code:"ABV", rentFactor:1.05 },
      portharcourt: { label:"Port Harcourt", code:"PHC", rentFactor:0.75 }
    },
    // Rent is modeled as a share of gross pay, not a flat market figure --
    // a flat ₦250k/month applied to every salary made low earners (e.g.
    // ₦70k/month) show wildly negative take-home, since nobody earning
    // that little is actually renting a ₦250k/month apartment. 0.40 is
    // calibrated so a ~₦600k/month earner in Lagos lands close to the old
    // flat-₦250k figure; it scales down sensibly for lower salaries.
    nigeriaRentShareOfGross: 0.40,
    nigeriaTaxRate: 0.12,
    nigeriaGrowth: 0.05,
    ukRate: 2000,

    professions: [
      { id:"swe",     label:"Software Engineer",        ukGBP:4200 },
      { id:"nurse",   label:"Registered Nurse",         ukGBP:2600 },
      { id:"acct",    label:"Accountant",               ukGBP:3100 },
      { id:"teacher", label:"Secondary School Teacher", ukGBP:2900 },
      { id:"civeng",  label:"Civil Engineer",           ukGBP:3300 },
      { id:"analyst", label:"Data Analyst",             ukGBP:3400 },
      { id:"doctor",  label:"Medical Doctor",           ukGBP:5200 },
      { id:"mktg",    label:"Marketing Manager",        ukGBP:3600 },
      { id:"design",  label:"Graphic Designer",         ukGBP:2500 },
      { id:"mecheng", label:"Mechanical Engineer",      ukGBP:3300 },
      { id:"pharm",   label:"Pharmacist",               ukGBP:3300 },
      { id:"lawyer",  label:"Lawyer",                   ukGBP:4000 }
    ],

    destinations: [
      { id:"uk", label:"United Kingdom", flag:"🇬🇧", currency:"GBP", symbol:"£", suffix:false,
        rate:2000, factor:1.00, taxRate:0.28, rent:1400, growth:0.035, visa:3,
        visaNote:"Student Route — well-trodden for Nigerians via licensed university sponsors; Graduate Route gives 2 years post-study work.",
        studyMonths:"12–15 months", studyDuration:1.1 },
      { id:"canada", label:"Canada", flag:"🇨🇦", currency:"CAD", symbol:"CA$", suffix:false,
        rate:1050, factor:0.95, taxRate:0.25, rent:1800, growth:0.04, visa:4,
        visaNote:"Study Permit — proof-of-funds scrutiny and 2024 intake caps have raised refusal rates for Nigerian applicants.",
        studyMonths:"16–24 months", studyDuration:1.65 },
      { id:"germany", label:"Germany", flag:"🇩🇪", currency:"EUR", symbol:"€", suffix:false,
        rate:1650, factor:1.05, taxRate:0.30, rent:950, growth:0.03, visa:3,
        visaNote:"National student visa — blocked account (~€11,900/yr) and B1/B2 German are the main hurdles, process is predictable.",
        studyMonths:"18–24 months", studyDuration:1.75 },
      { id:"poland", label:"Poland", flag:"🇵🇱", currency:"PLN", symbol:"zł", suffix:true,
        rate:380, factor:0.55, taxRate:0.20, rent:2600, growth:0.06, visa:2,
        visaNote:"EU national student visa — lower financial threshold, decent approval rates, Schengen access.",
        studyMonths:"12 months", studyDuration:1.0 },
      { id:"ireland", label:"Ireland", flag:"🇮🇪", currency:"EUR", symbol:"€", suffix:false,
        rate:1650, factor:1.10, taxRate:0.28, rent:1600, growth:0.035, visa:3,
        visaNote:"Non-EEA student visa — tuition paid upfront plus proof of funds; Stamp 1G gives up to 2 years post-study work.",
        studyMonths:"12–16 months", studyDuration:1.15 }
    ]
  };

  var state = { profession:null, salary:null, city:"lagos", destination:null, spouse:false, children:0, familyOpen:false, calculated:false };

  var $ = function(id){ return document.getElementById(id); };
  function fmt(n){ return Math.round(n).toLocaleString('en-US'); }
  function money(n, symbol, suffix){
    var neg = n < 0;
    var body = suffix ? (fmt(Math.abs(n)) + " " + symbol) : (symbol + fmt(Math.abs(n)));
    return neg ? ('-' + body) : body;
  }

  // ---------- live FX rates ----------
  // Fetched from our own backend (/api/fx), which calls a free keyless FX API
  // server-side, caches it, and always returns a usable rate set — live if the
  // upstream call succeeded recently, illustrative fallback otherwise.
  var fx = { live:false, asOf:null };

  function applyLiveRates(json){
    var r = json.rates;
    if(!r) return false;
    if(r.GBP) DATA.ukRate = r.GBP;
    DATA.destinations.forEach(function(d){
      if(r[d.currency]) d.rate = r[d.currency];
    });
    fx.live = !!json.live;
    fx.asOf = json.asOf;
    return true;
  }

  function refreshFxBadge(){
    var badge = $('fxBadge'), text = $('fxBadgeText');
    badge.classList.toggle('live', fx.live);
    text.textContent = fx.live
      ? ('Live exchange rates · updated ' + fx.asOf)
      : 'Illustrative exchange rates (live feed unavailable right now)';
  }

  fetch('/api/fx').then(function(res){ return res.json(); }).then(function(json){
    applyLiveRates(json);
    refreshFxBadge();
    if(state.calculated) runCalculation();
  }).catch(function(){ refreshFxBadge(); });

  // ---------- populate professions ----------
  var professionList = $('professions');
  DATA.professions.forEach(function(p){
    var opt = document.createElement('option');
    opt.value = p.label;
    professionList.appendChild(opt);
  });

  // ---------- destination chips ----------
  var destWrap = $('destinations');
  DATA.destinations.forEach(function(d){
    var el = document.createElement('button');
    el.type = 'button';
    el.className = 'destchip';
    el.dataset.id = d.id;
    el.innerHTML = '<span class="flag">'+d.flag+'</span><span class="name">'+d.label+'</span><span class="curr">'+d.currency+'</span>';
    el.addEventListener('click', function(){
      state.destination = d.id;
      Array.prototype.forEach.call(destWrap.children, function(c){ c.classList.remove('active'); });
      el.classList.add('active');
      updateCalcButton();
      if(state.calculated) runCalculation();
    });
    destWrap.appendChild(el);
  });

  function findProfession(label){
    label = (label||'').trim().toLowerCase();
    for(var i=0;i<DATA.professions.length;i++){ if(DATA.professions[i].label.toLowerCase()===label) return DATA.professions[i]; }
    return null;
  }
  function findDestination(id){
    for(var i=0;i<DATA.destinations.length;i++){ if(DATA.destinations[i].id===id) return DATA.destinations[i]; }
    return null;
  }

  function updateCalcButton(){
    var salaryVal = parseFloat(($('salary').value||'').replace(/,/g,''));
    var prof = findProfession($('profession').value);
    var ok = prof && salaryVal > 0 && state.destination;
    $('calcBtn').disabled = !ok;
  }

  $('profession').addEventListener('input', updateCalcButton);
  $('salary').addEventListener('input', function(){
    var v = this.value.replace(/[^0-9]/g,'');
    this.value = v ? Number(v).toLocaleString('en-US') : '';
    updateCalcButton();
    if(state.calculated) runCalculation();
  });
  $('city').addEventListener('change', function(){ state.city = this.value; if(state.calculated) runCalculation(); });

  // ---------- family mode ----------
  $('familyToggleBtn').addEventListener('click', function(){
    state.familyOpen = !state.familyOpen;
    $('familyPanel').classList.toggle('show', state.familyOpen);
    this.classList.toggle('on', state.familyOpen);
  });
  $('famSpouse').addEventListener('change', function(){ state.spouse = this.checked; if(state.calculated) runCalculation(); });
  $('famMinus').addEventListener('click', function(){ state.children = Math.max(0, state.children-1); $('famCount').textContent = state.children; if(state.calculated) runCalculation(); });
  $('famPlus').addEventListener('click', function(){ state.children = Math.min(6, state.children+1); $('famCount').textContent = state.children; if(state.calculated) runCalculation(); });

  // ---------- calculation engine ----------
  function computeForYear(profession, city, dest, spouse, children, year){
    var cityData = DATA.cities[city];
    var householdMult = 1 + (spouse?0.4:0) + children*0.25;

    var salaryInputNaira = parseFloat(($('salary').value||'0').replace(/,/g,''));
    var nairaGross = salaryInputNaira * Math.pow(1+DATA.nigeriaGrowth, year);
    var nairaRentBase = nairaGross * DATA.nigeriaRentShareOfGross;
    var nairaRent = nairaRentBase * cityData.rentFactor * householdMult;
    var nairaChildCost = children * (nairaRentBase * cityData.rentFactor) * 0.15;
    var nairaTax = nairaGross * DATA.nigeriaTaxRate;
    var nairaNet = nairaGross - nairaTax - nairaRent - nairaChildCost;

    var ukBaselineNGN = profession.ukGBP * DATA.ukRate;
    var foreignLocalGross = (ukBaselineNGN * dest.factor / dest.rate) * Math.pow(1+dest.growth, year);
    var foreignRent = dest.rent * householdMult;
    var foreignChildCost = children * dest.rent * 0.3;
    var foreignTax = foreignLocalGross * dest.taxRate;
    var foreignNetLocal = foreignLocalGross - foreignTax - foreignRent - foreignChildCost;
    var foreignNetNGN = foreignNetLocal * dest.rate;

    return { nairaNet:nairaNet, foreignNetLocal:foreignNetLocal, foreignNetNGN:foreignNetNGN, nairaGross:nairaGross, foreignLocalGross:foreignLocalGross };
  }

  // Illustrative assumption: while studying, income abroad is limited to
  // modest part-time work (common student-visa allowance), not the full
  // qualified-professional salary -- that only starts at graduation. This is
  // what turns the trajectory into a real staged path (low during study,
  // a step up at graduation, growth from there) instead of a smooth curve
  // that implies full foreign pay from day one.
  var DURING_STUDY_INCOME_FACTOR = 0.2;

  function computeDestNet(profession, dest, spouse, children, year){
    var householdMult = 1 + (spouse?0.4:0) + children*0.25;
    var ukBaselineNGN = profession.ukGBP * DATA.ukRate;
    var baselineLocalGross = ukBaselineNGN * dest.factor / dest.rate;
    var rent = dest.rent * householdMult;
    var childCost = children * dest.rent * 0.3;
    var studying = year < dest.studyDuration;

    var localGross = studying
      ? baselineLocalGross * DURING_STUDY_INCOME_FACTOR
      : baselineLocalGross * Math.pow(1+dest.growth, year - dest.studyDuration);

    var tax = localGross * dest.taxRate;
    var netLocal = localGross - tax - rent - childCost;
    return { foreignNetLocal:netLocal, foreignNetNGN:netLocal*dest.rate, phase: studying ? 'study' : 'working' };
  }

  // Illustrative: many students plan to return to Nigeria after finishing
  // the Master's rather than stay abroad. An internationally earned
  // qualification typically commands a real premium in the Nigerian job
  // market -- modeled here as a one-time multiplier applied to what the
  // person's Nigeria salary would have grown to by graduation, then
  // growing at the normal local rate from there. This is a rough,
  // clearly-illustrative assumption (not a benchmarked figure), same as
  // the study-phase income factor above.
  var RETURNEE_QUALIFICATION_PREMIUM = 1.6;

  function computeNigeriaReturneeNet(city, spouse, children, studyDuration, year){
    var cityData = DATA.cities[city];
    var householdMult = 1 + (spouse?0.4:0) + children*0.25;
    var salaryInputNaira = parseFloat(($('salary').value||'0').replace(/,/g,''));
    var grossAtReturn = salaryInputNaira * Math.pow(1+DATA.nigeriaGrowth, studyDuration) * RETURNEE_QUALIFICATION_PREMIUM;
    var yearsSinceReturn = Math.max(0, year - studyDuration);
    var gross = grossAtReturn * Math.pow(1+DATA.nigeriaGrowth, yearsSinceReturn);
    var rentBase = gross * DATA.nigeriaRentShareOfGross;
    var rent = rentBase * cityData.rentFactor * householdMult;
    var childCost = children * (rentBase * cityData.rentFactor) * 0.15;
    var tax = gross * DATA.nigeriaTaxRate;
    var net = gross - tax - rent - childCost;
    return { nairaNet: net, nairaGross: gross };
  }

  function yearLabel(y){
    if(y === 0) return 'Now';
    return Number.isInteger(y) ? ('Year '+y) : ('Yr '+y.toFixed(1));
  }

  // Builds the milestone years plotted on the trajectory chart: today, the
  // midpoint of study, graduation, six months into the new job, then yearly
  // out to year 5 -- so the shape actually shows the staged path rather than
  // sampling only at round years and smoothing over the step.
  function buildMilestoneYears(studyDuration){
    var pts = [0, studyDuration/2, studyDuration, studyDuration+0.5];
    [1,2,3,4,5].forEach(function(y){ if(y > pts[pts.length-1] + 0.05) pts.push(y); });
    if(pts[pts.length-1] < 5) pts.push(5);
    pts = pts.map(function(y){ return Math.round(Math.min(5, Math.max(0, y))*100)/100; });
    var seen = {};
    var deduped = [];
    pts.forEach(function(y){ if(!seen[y]){ seen[y]=true; deduped.push(y); } });
    deduped.sort(function(a,b){ return a-b; });
    return deduped;
  }

  // Piecewise-linear map from the pay ratio onto a 0-100 "ROI Score",
  // anchored so the verdict-tier boundaries land on round score values.
  function scoreFromRatio(ratio){
    var points = [ [0,5], [0.9,34], [1.4,55], [2.5,80], [4.0,97] ];
    if(ratio <= points[0][0]) return points[0][1];
    for(var i=0;i<points.length-1;i++){
      var a = points[i], b = points[i+1];
      if(ratio <= b[0]){
        var t = (ratio - a[0]) / (b[0] - a[0]);
        return Math.round(a[1] + t * (b[1] - a[1]));
      }
    }
    return points[points.length-1][1];
  }

  function verdictFor(ratio){
    if(ratio >= 2.5) return { text:"Strong case to study abroad", sub:"The earning upside clears rent, tax and cost of living by a wide margin — this is the profile the trajectory chart below is worth studying." };
    if(ratio >= 1.4) return { text:"Promising — worth exploring", sub:"A real uplift once qualified abroad. The visa route and 5-year growth curve are the deciding factors." };
    if(ratio >= 0.9) return { text:"Mixed — weigh the full picture", sub:"Year-one numbers are close. The 5-year trajectory below is the tie-breaker." };
    return { text:"Nigeria holds its own for now", sub:"After rent and tax, this role doesn't clearly gain from a move yet — the growth curve may still change that." };
  }

  function runCalculation(){
    var prof = findProfession($('profession').value);
    var dest = findDestination(state.destination);
    if(!prof || !dest) return;
    state.profession = prof; state.calculated = true;

    var cityLabel = DATA.cities[state.city].label;
    var y0 = computeForYear(prof, state.city, dest, state.spouse, state.children, 0);
    // The headline ROI compares today's actual Nigeria pay against the
    // destination salary you'd actually earn once qualified (i.e. right at
    // graduation) -- not an immediate foreign salary, since that's not real.
    var destAtGrad = computeDestNet(prof, dest, state.spouse, state.children, dest.studyDuration);
    var ratio = destAtGrad.foreignNetNGN / y0.nairaNet;
    var score = scoreFromRatio(ratio);
    var v = verdictFor(ratio);

    $('bpFrom').textContent = DATA.cities[state.city].code;
    $('bpTo').textContent = dest.id === 'uk' ? 'LON' : dest.id==='canada' ? 'YYZ' : dest.id==='germany' ? 'BER' : dest.id==='poland' ? 'WAW' : 'DUB';
    $('bpProfession').textContent = ' · ' + prof.label;
    $('bpVerdict').innerHTML = score + '<span style="font-size:0.4em; color:var(--text-muted);">/100</span>';
    $('bpSub').textContent = v.text + ' — ' + v.sub;
    $('bpNaira').textContent = money(y0.nairaNet, '₦', false) + '/mo';
    $('bpForeign').textContent = money(destAtGrad.foreignNetLocal, dest.symbol, dest.suffix) + '/mo';
    $('bpMultiplier').textContent = ratio.toFixed(1) + 'x';

    var bars = '';
    for(var i=1;i<=5;i++){ bars += '<i class="'+(i<=dest.visa?'on':'')+'"></i>'; }
    $('visaBars').innerHTML = bars;
    var visaWords = ['Very easy','Easy','Moderate','Hard','Very hard'];
    $('visaNote').textContent = visaWords[dest.visa-1] + ' (' + dest.visa + '/5) — ' + dest.visaNote;

    $('legendNigeria').textContent = 'Without further study (' + cityLabel + ')';
    $('legendDest').textContent = 'With a Master\'s in ' + dest.label;
    $('thNigeria').textContent = 'Without study (₦/mo)';
    $('thDest').textContent = 'With Master\'s (₦-equiv/mo)';

    $('pivotHeadline').textContent = 'Ready to unlock this score as a ' + prof.label + '?';
    $('pivotBody').textContent = 'A Master\'s at one of TGM\'s 12 partner universities in ' + dest.label + ' can get you there in ' + dest.studyMonths + ' — a real admission pathway, not just a plan.';

    // Milestone years trace the actual staged path (studying -> graduation ->
    // working) rather than sampling only at round years, which is what makes
    // the destination curve step up at graduation instead of looking like
    // smooth, immediate foreign pay from day one.
    var years = buildMilestoneYears(dest.studyDuration);
    var nigeriaSeries = years.map(function(y){ return computeForYear(prof, state.city, dest, state.spouse, state.children, y).nairaNet; });
    var destSeries = years.map(function(y){ return computeDestNet(prof, dest, state.spouse, state.children, y).foreignNetNGN; });
    renderChart(years, nigeriaSeries, destSeries, 'Without further study', 'With a Master\'s abroad', dest.studyDuration);
    renderTable(years, nigeriaSeries, destSeries);

    var destDuringStudy = computeDestNet(prof, dest, state.spouse, state.children, 0);
    // Alternative path: return to Nigeria after graduating instead of staying
    // abroad. Uses the qualification-premium model above, not the "stay
    // abroad" destination figures.
    var returneeAtGrad = computeNigeriaReturneeNet(state.city, state.spouse, state.children, dest.studyDuration, dest.studyDuration);
    var returneeYear5 = computeNigeriaReturneeNet(state.city, state.spouse, state.children, dest.studyDuration, 5);
    renderPathBreakdown(prof, dest, cityLabel, y0, destDuringStudy, destAtGrad, ratio, v,
      nigeriaSeries[nigeriaSeries.length-1], destSeries[destSeries.length-1], returneeAtGrad, returneeYear5);

    $('results').classList.add('show');
    lastCalc = { prof:prof, dest:dest, ratio:ratio, score:score, v:v, y0:y0, destAtGrad:destAtGrad };
  }

  // ---------- plain-English breakdown ----------
  function renderPathBreakdown(prof, dest, cityLabel, y0, destDuringStudy, destAtGrad, ratio, v, finalNigeriaNGN, finalDestNGN, returneeAtGrad, returneeYear5){
    var safeRatio = isFinite(ratio) ? ratio : 0;
    var returneeRatio = returneeAtGrad.nairaNet / y0.nairaNet;
    var interpretation =
      'Right now, as a ' + prof.label + ' in ' + cityLabel + ', you take home about ' + money(y0.nairaNet,'₦',false) + '/month. ' +
      'A Master\'s in ' + dest.label + ' takes about ' + dest.studyMonths + ' — during that time, expect only modest part-time income, around ' +
      money(destDuringStudy.foreignNetLocal, dest.symbol, dest.suffix) + '/month. ' +
      'Once you graduate, a ' + prof.label + ' role there could pay around ' + money(destAtGrad.foreignNetLocal, dest.symbol, dest.suffix) +
      '/month — about ' + Math.max(safeRatio,0).toFixed(1) + 'x your current take-home — growing toward roughly ' + money(finalDestNGN,'₦',false) +
      '/month (₦-equivalent) by year 5. ' + v.sub + ' ' +
      'And if you come back to Nigeria after the Master\'s instead of staying in ' + dest.label + ', the qualification itself is usually worth a real premium here too — realistically around ' +
      money(returneeAtGrad.nairaNet,'₦',false) + '/month in ' + cityLabel + ' right after you return (about ' + Math.max(returneeRatio,0).toFixed(1) + 'x your current take-home), ' +
      'growing toward roughly ' + money(returneeYear5.nairaNet,'₦',false) + '/month by year 5 — so the degree still pays off even if you don\'t stay abroad.';
    $('pathInterpretation').textContent = interpretation;

    var steps = [
      { label: 'Now', detail: prof.label + ' in ' + cityLabel + ', earning ' + money(y0.nairaNet,'₦',false) + '/mo.' },
      { label: 'Apply & get admission', detail: 'TGM matches you to partner universities in ' + dest.label + '.' },
      { label: 'Study (' + dest.studyMonths + ')', detail: 'Limited part-time income only, around ' + money(destDuringStudy.foreignNetLocal, dest.symbol, dest.suffix) + '/mo.' },
      { label: 'Graduate', detail: 'Qualified and ready to work in ' + dest.label + ' — or back home.' },
      { label: 'Option A: Stay in ' + dest.label, detail: 'From about ' + money(destAtGrad.foreignNetLocal, dest.symbol, dest.suffix) + '/mo, growing to ' + money(finalDestNGN,'₦',false) + '/mo (₦-equiv) by year 5.' },
      { label: 'Option B: Return to ' + cityLabel, detail: 'Your international qualification still commands a premium — about ' + money(returneeAtGrad.nairaNet,'₦',false) + '/mo on return, growing to ' + money(returneeYear5.nairaNet,'₦',false) + '/mo by year 5.' },
      { label: 'Either way, vs. not studying further', detail: money(finalNigeriaNGN,'₦',false) + '/mo by year 5 if you\'d stayed on your current path with no further study.' }
    ];
    $('pathSteps').innerHTML = steps.map(function(s,i){
      return '<li><span class="step-n">'+(i+1)+'</span><span class="step-body"><b>'+s.label+'</b><br>'+s.detail+'</span></li>';
    }).join('');
  }

  var lastCalc = null;

  $('calcBtn').addEventListener('click', function(){
    runCalculation();
    $('results').scrollIntoView({ behavior:'smooth', block:'start' });
  });

  // ---------- chart ----------
  // lastChartData holds the raw (₦) series from the most recent calculation;
  // chartView toggles how drawChart() renders it without recomputing anything.
  var lastChartData = null;
  var chartView = 'value'; // 'value' | 'growth'

  function formatNaira(v){ return v>=1000000 ? (v/1000000).toFixed(1)+'M' : Math.round(v/1000)+'k'; }
  function formatPct(v){ return (v>=0?'+':'') + Math.round(v) + '%'; }

  // Finds the fractional year at which s1 (Nigeria) and s2 (destination)
  // swap which one is higher, if that happens within the plotted horizon.
  // Returns null if the two never cross (the common case, since destination
  // pay already assumes the qualification is in hand).
  function findCrossing(years, s1, s2){
    for(var i=1;i<years.length;i++){
      var prevDiff = s1[i-1]-s2[i-1];
      var currDiff = s1[i]-s2[i];
      if(prevDiff === 0) return years[i-1];
      if((prevDiff<0) !== (currDiff<0)){
        var t = Math.abs(prevDiff) / (Math.abs(prevDiff)+Math.abs(currDiff));
        return years[i-1] + t*(years[i]-years[i-1]);
      }
    }
    return null;
  }

  function renderChart(years, s1, s2, label1, label2, graduationYear){
    lastChartData = { years:years, s1:s1, s2:s2, label1:label1, label2:label2, graduationYear:graduationYear };
    drawChart();
  }

  function drawChart(){
    if(!lastChartData) return;
    var years = lastChartData.years, rawS1 = lastChartData.s1, rawS2 = lastChartData.s2;
    var label1 = lastChartData.label1, label2 = lastChartData.label2;
    var horizon = years[years.length-1];

    // The destination series is indexed to its graduation-point value, not
    // year 0 -- year 0 for that series is the "still studying, part-time
    // income" phase, which is often near zero or negative after rent, so it
    // can't be a meaningful 100% baseline. Nigeria has no such phase, so it
    // still indexes from today (year 0) as before.
    var gradYear = lastChartData.graduationYear;
    var gradIdx = 0;
    if(gradYear !== undefined){
      var bestDiff = Infinity;
      years.forEach(function(yr, i){ var d = Math.abs(yr-gradYear); if(d<bestDiff){ bestDiff=d; gradIdx=i; } });
    }

    // % growth is only meaningful against a positive baseline -- a very low
    // salary can leave net pay at or below zero after rent and tax, which
    // would otherwise turn indexing into NaN/Infinity. Fall back to the
    // ₦ value view for that combination rather than render a broken chart.
    var canIndex = rawS1[0] > 0 && rawS2[gradIdx] > 0;
    var growthMode = chartView === 'growth' && canIndex;
    var growthBtn = $('chartViewToggle').querySelector('[data-view="growth"]');
    growthBtn.disabled = !canIndex;
    var disabledNote = $('growthDisabledNote');
    disabledNote.classList.toggle('show', !canIndex);
    if(!canIndex){
      disabledNote.textContent = '% Growth isn\'t available here: ' +
        (rawS1[0] <= 0 ? 'your year-0 net pay in Nigeria is ₦0 or below after rent and tax, ' : 'the destination\'s post-graduation net pay is ₦0 or below after rent and tax, ') +
        'so a percentage change from that starting point is undefined. Showing ₦ Value instead.';
    }

    // Nigeria indexes from today (=100); the destination indexes from its
    // graduation-point value (=100) for the reason above -- so points before
    // graduation show up as a percentage of the post-graduation salary, not
    // of an unstable near-zero study-phase number.
    var s1 = growthMode ? rawS1.map(function(v){ return (v/rawS1[0])*100; }) : rawS1;
    var s2 = growthMode ? rawS2.map(function(v){ return (v/rawS2[gradIdx])*100; }) : rawS2;

    // Old svg node is swapped for a clone so mousemove/mouseleave listeners
    // from previous renders don't pile up every time inputs change.
    var oldSvg = $('chartSvg');
    var svg = oldSvg.cloneNode(false);
    oldSvg.parentNode.replaceChild(svg, oldSvg);

    var W = 560, H = 236, padL = 44, padR = 16, padT = 28, padB = 28;
    var allValues = s1.concat(s2);
    var maxV = Math.max.apply(null, allValues) * 1.08;
    // In ₦ Value mode the floor is normally 0, but if net pay actually dips
    // negative (a very low salary after rent/tax), extend the floor below it
    // instead of clipping those points off the bottom of the chart.
    var dataMin = Math.min.apply(null, allValues);
    var minV = growthMode ? dataMin * 0.95 : Math.min(0, dataMin * 1.15);

    // x is mapped by actual year value (not array index), since milestone
    // years are unevenly spaced -- that's what lets the destination curve
    // show a real flat-then-step-then-climb shape instead of a smooth line.
    function x(yr){ return padL + (W-padL-padR) * (yr/horizon); }
    function y(v){ return padT + (H-padT-padB) * (1 - (v-minV)/(maxV-minV)); }
    function formatAxis(v){ return growthMode ? Math.round(v)+'%' : formatNaira(v); }

    var gridlines = '';
    var ticks = 4;
    for(var g=0; g<=ticks; g++){
      var gv = minV + (maxV-minV) * g/ticks;
      var gy = y(gv);
      gridlines += '<line x1="'+padL+'" y1="'+gy+'" x2="'+(W-padR)+'" y2="'+gy+'" stroke="var(--line)" stroke-width="1"/>';
      gridlines += '<text x="'+(padL-8)+'" y="'+(gy+3)+'" font-size="9" text-anchor="end" fill="var(--text-muted)" font-family="Plex Data, monospace">'+formatAxis(gv)+'</text>';
    }
    // Axis tick labels stay at round years regardless of how many milestone
    // data points feed the curve itself.
    var xlabels = '';
    for(var yr=0; yr<=horizon; yr++){
      xlabels += '<text x="'+x(yr)+'" y="'+(H-8)+'" font-size="9.5" text-anchor="middle" fill="var(--text-muted)" font-family=\'Plex Data, monospace\'>'+(yr===0?'Now':'Yr '+yr)+'</text>';
    }

    function path(series){
      return series.map(function(v,i){ return (i===0?'M':'L') + x(years[i]).toFixed(1) + ',' + y(v).toFixed(1); }).join(' ');
    }
    function areaPath(series){
      return path(series) +
        ' L'+x(years[years.length-1]).toFixed(1)+','+(H-padB) +
        ' L'+x(years[0]).toFixed(1)+','+(H-padB)+' Z';
    }
    function dots(series, color){
      return series.map(function(v,i){ return '<circle class="pt" data-i="'+i+'" cx="'+x(years[i]).toFixed(1)+'" cy="'+y(v).toFixed(1)+'" r="4" fill="'+color+'" stroke="var(--surface-raised)" stroke-width="1.5"/>'; }).join('');
    }

    var rawLast1 = rawS1[rawS1.length-1], rawLast2 = rawS2[rawS2.length-1];
    var growth1 = rawS1[0] > 0 ? (((rawLast1/rawS1[0])-1)*100) : null;
    var growth2 = rawS2[gradIdx] > 0 ? (((rawLast2/rawS2[gradIdx])-1)*100) : null;
    var last1 = s1[s1.length-1], last2 = s2[s2.length-1];
    var lastX = x(years[years.length-1]);

    var growthLabel1 = growth1 === null ? '—' : (formatPct(growth1) + ' / 5yr');
    var growthLabel2 = growth2 === null ? '—' : (formatPct(growth2) + ' since grad.');
    var mainLabel1 = growthMode ? (growth1===null?'—':formatPct(growth1)) : formatNaira(rawLast1);
    var subLabel1  = growthMode ? formatNaira(rawLast1) : growthLabel1;
    var mainLabel2 = growthMode ? (growth2===null?'—':formatPct(growth2)) : formatNaira(rawLast2);
    var subLabel2  = growthMode ? formatNaira(rawLast2) : growthLabel2;

    var endLabels =
      '<text x="'+(lastX+6)+'" y="'+(y(last1)+3)+'" font-size="10" fill="var(--series-nigeria)" font-family=\'Plex Data, monospace\' font-weight="600">'+mainLabel1+'</text>' +
      '<text x="'+(lastX+6)+'" y="'+(y(last1)+15)+'" font-size="8.5" fill="var(--text-muted)" font-family=\'Plex Data, monospace\'>'+subLabel1+'</text>' +
      '<text x="'+(lastX+6)+'" y="'+(y(last2)+3)+'" font-size="10" fill="var(--series-dest)" font-family=\'Plex Data, monospace\' font-weight="600">'+mainLabel2+'</text>' +
      '<text x="'+(lastX+6)+'" y="'+(y(last2)+15)+'" font-size="8.5" fill="var(--text-muted)" font-family=\'Plex Data, monospace\'>'+subLabel2+'</text>';

    // Crossover marker is computed on the raw ₦ series regardless of view
    // mode -- "when does actual pay parity happen" is only meaningful in
    // real Naira terms, not on the indexed growth curve.
    var crossingYear = findCrossing(years, rawS1, rawS2);
    var crossingMarkup = '';
    if(crossingYear !== null && crossingYear >= years[0] && crossingYear <= horizon){
      var cx = x(crossingYear);
      crossingMarkup =
        '<line x1="'+cx+'" y1="'+padT+'" x2="'+cx+'" y2="'+(H-padB)+'" stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="4,3"/>' +
        '<text x="'+cx+'" y="'+(padT-8)+'" font-size="9" text-anchor="middle" fill="var(--accent)" font-family="Plex Data, monospace" font-weight="600">Crossover · Yr '+crossingYear.toFixed(1)+'</text>';
    }

    svg.innerHTML =
      gridlines + xlabels +
      '<path d="'+areaPath(s1)+'" fill="var(--series-nigeria)" opacity="0.10" stroke="none"/>' +
      '<path d="'+areaPath(s2)+'" fill="var(--series-dest)" opacity="0.10" stroke="none"/>' +
      '<path d="'+path(s1)+'" fill="none" stroke="var(--series-nigeria)" stroke-width="2" stroke-linecap="round"/>' +
      '<path d="'+path(s2)+'" fill="none" stroke="var(--series-dest)" stroke-width="2" stroke-linecap="round"/>' +
      dots(s1, 'var(--series-nigeria)') + dots(s2, 'var(--series-dest)') +
      endLabels + crossingMarkup +
      '<line id="crosshair" x1="0" y1="'+padT+'" x2="0" y2="'+(H-padB)+'" stroke="var(--text-muted)" stroke-width="1" stroke-dasharray="3,3" opacity="0"/>';

    var tooltip = $('chartTooltip');
    var wrap = $('chartWrap');
    svg.addEventListener('mousemove', function(evt){
      var rect = svg.getBoundingClientRect();
      var relX = (evt.clientX - rect.left) / rect.width * W;
      var yearAtMouse = ((relX - padL) / (W-padL-padR)) * horizon;
      // Snap to the nearest milestone point rather than assuming uniform
      // spacing, since milestone years aren't evenly spaced.
      var idx = 0, best = Infinity;
      years.forEach(function(yr, i){
        var d = Math.abs(yr - yearAtMouse);
        if(d < best){ best = d; idx = i; }
      });
      var cross = $('crosshair');
      var px1 = x(years[idx]);
      cross.setAttribute('x1', px1); cross.setAttribute('x2', px1); cross.setAttribute('opacity','1');
      var wrapRect = wrap.getBoundingClientRect();
      var px = (px1/W) * wrapRect.width;
      tooltip.style.left = px + 'px';
      tooltip.style.top = ((y(Math.max(s1[idx],s2[idx]))/H) * wrapRect.height) + 'px';
      tooltip.innerHTML =
        '<div style="font-weight:600; margin-bottom:2px;">'+yearLabel(years[idx])+'</div>' +
        '<div class="row"><span class="sw" style="background:var(--series-nigeria)"></span>'+label1+': '+(growthMode ? formatPct(s1[idx]-100)+' · ' : '')+'₦'+fmt(rawS1[idx])+'</div>' +
        '<div class="row"><span class="sw" style="background:var(--series-dest)"></span>'+label2+': '+(growthMode ? formatPct(s2[idx]-100)+' · ' : '')+'₦'+fmt(rawS2[idx])+'</div>';
      tooltip.classList.add('show');
    });
    svg.addEventListener('mouseleave', function(){
      tooltip.classList.remove('show');
      var cross = $('crosshair'); if(cross) cross.setAttribute('opacity','0');
    });
  }

  $('chartViewToggle').addEventListener('click', function(evt){
    var btn = evt.target.closest('button[data-view]');
    if(!btn || btn.classList.contains('active') || btn.disabled) return;
    Array.prototype.forEach.call(this.querySelectorAll('button'), function(b){ b.classList.remove('active'); });
    btn.classList.add('active');
    chartView = btn.dataset.view;
    drawChart();
  });

  function renderTable(years, s1, s2){
    var body = $('dataTableBody');
    body.innerHTML = years.map(function(yr,i){
      return '<tr><td>'+yearLabel(yr)+'</td><td class="num">₦'+fmt(s1[i])+'</td><td class="num">₦'+fmt(s2[i])+'</td></tr>';
    }).join('');
  }
  $('tableToggle').addEventListener('click', function(){
    var t = $('dataTable');
    var showing = t.classList.toggle('show');
    this.textContent = showing ? 'Hide table' : 'View as table';
  });

  // ---------- share link ----------
  $('shareBtn').addEventListener('click', function(){ buildShareLink(true); });
  $('copyLinkBtn').addEventListener('click', function(){ buildShareLink(true); });
  function buildShareLink(copy){
    if(!lastCalc) return;
    var params = new URLSearchParams();
    params.set('profession', lastCalc.prof.label);
    params.set('salary', ($('salary').value||'').replace(/,/g,''));
    params.set('city', state.city);
    params.set('dest', lastCalc.dest.id);
    var url = location.origin + location.pathname + '?' + params.toString();
    if(copy && navigator.clipboard){
      navigator.clipboard.writeText(url).then(function(){
        var btn = $('shareBtn');
        var original = btn.innerHTML;
        btn.innerHTML = '✓ Link copied';
        setTimeout(function(){ btn.innerHTML = original; }, 1800);
      }).catch(function(){ prompt('Copy this link:', url); });
    }
    return url;
  }

  function prefillFromQuery(){
    var params = new URLSearchParams(location.search);
    if(!params.has('profession')) return;
    $('profession').value = params.get('profession') || '';
    var salary = params.get('salary');
    if(salary){ $('salary').value = Number(salary).toLocaleString('en-US'); }
    var city = params.get('city'); if(city){ $('city').value = city; state.city = city; }
    var dest = params.get('dest');
    if(dest){
      state.destination = dest;
      Array.prototype.forEach.call(destWrap.children, function(c){ c.classList.toggle('active', c.dataset.id===dest); });
    }
    updateCalcButton();
    if(!$('calcBtn').disabled){ runCalculation(); }
  }
  prefillFromQuery();

  // ---------- modal / real lead capture ----------
  function openModal(){ $('modalBackdrop').classList.add('show'); }
  function closeModal(){
    $('modalBackdrop').classList.remove('show');
    $('modalForm').classList.remove('hide');
    $('modalSuccess').classList.remove('show');
    $('modalError').classList.remove('show');
    $('leadSubmit').disabled = false;
    $('leadSubmit').textContent = 'Send me my options';
  }
  $('pivotBtn').addEventListener('click', openModal);
  $('modalClose').addEventListener('click', closeModal);
  $('modalBackdrop').addEventListener('click', function(e){ if(e.target===this) closeModal(); });

  $('leadSubmit').addEventListener('click', function(){
    var email = $('leadEmail').value.trim();
    var errEl = $('modalError');
    if(!email || email.indexOf('@')===-1){
      $('leadEmail').style.borderColor = '#c0392b';
      errEl.textContent = 'Enter a valid email address.';
      errEl.classList.add('show');
      return;
    }
    $('leadEmail').style.borderColor = '';
    errEl.classList.remove('show');

    var btn = this;
    btn.disabled = true;
    btn.textContent = 'Sending…';

    var payload = {
      email: email,
      qualification: $('leadQual').value,
      grade: $('leadGrade').value,
      profession: lastCalc ? lastCalc.prof.label : ($('profession').value || ''),
      destination: lastCalc ? lastCalc.dest.label : '',
      city: DATA.cities[state.city] ? DATA.cities[state.city].label : state.city,
      salary: parseFloat(($('salary').value||'0').replace(/,/g,'')) || 0,
      score: lastCalc ? lastCalc.score : null,
      ratio: lastCalc ? Number(lastCalc.ratio.toFixed(2)) : null,
      source: 'Global Education ROI'
    };

    fetch('/api/leads', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function(res){
      return res.json().then(function(data){ return { ok: res.ok, data: data }; });
    }).then(function(result){
      if(!result.ok){
        btn.disabled = false;
        btn.textContent = 'Send me my options';
        errEl.textContent = (result.data && result.data.error) || 'Something went wrong — try again.';
        errEl.classList.add('show');
        return;
      }
      btn.textContent = result.data.student_new ? 'Setting up your chat with Amara…' : 'Sending you a login code…';
      window.location.href = result.data.redirect || '/chat';
    }).catch(function(){
      btn.disabled = false;
      btn.textContent = 'Send me my options';
      errEl.textContent = 'Could not reach the server — check your connection and try again.';
      errEl.classList.add('show');
    });
  });

  // ---------- PNG report download ----------
  $('downloadBtn').addEventListener('click', function(){
    if(!lastCalc) return;
    document.fonts.ready.then(drawReportCanvas).then(function(){
      var canvas = $('reportCanvas');
      var link = document.createElement('a');
      link.download = 'global-education-roi-report.png';
      link.href = canvas.toDataURL('image/png');
      link.click();
    });
  });

  function drawReportCanvas(){
    var c = $('reportCanvas');
    var ctx = c.getContext('2d');
    var W = c.width, H = c.height;
    var dark = matchMedia('(prefers-color-scheme: dark)').matches;
    var rootTheme = document.documentElement.getAttribute('data-theme');
    if(rootTheme) dark = rootTheme==='dark';

    var bg = dark ? '#0A0F1E' : '#F5F7F1';
    var card = dark ? '#131A2E' : '#ffffff';
    var ink = dark ? '#EDEFE7' : '#0A0F1E';
    var muted = dark ? '#AEB6A4' : '#5B6357';
    var accent = dark ? '#F2A93B' : '#D98A22';
    var stamp = dark ? '#33C57A' : '#1F9D57';

    ctx.fillStyle = bg; ctx.fillRect(0,0,W,H);
    ctx.fillStyle = card; roundRect(ctx, 48,48,W-96,H-96,28); ctx.fill();

    ctx.fillStyle = accent;
    ctx.font = '600 26px "Plex Data"';
    ctx.fillText('GLOBAL EDUCATION', 90, 140);
    ctx.fillStyle = ink;
    ctx.font = '900 44px "Fraunces Display"';
    ctx.fillText('ROI', 90, 195);

    ctx.fillStyle = muted;
    ctx.font = '500 22px "Plex Data"';
    ctx.fillText((lastCalc.prof.label + ' · ' + DATA.cities[state.city].label + ' → ' + lastCalc.dest.label).toUpperCase(), 90, 240);

    ctx.fillStyle = stamp;
    ctx.font = '600 128px "Plex Data"';
    ctx.fillText(lastCalc.score + '/100', 90, 400);
    ctx.fillStyle = ink;
    ctx.font = '900 42px "Fraunces Display"';
    wrapText(ctx, lastCalc.v.text, 90, 470, W-260, 48);

    ctx.fillStyle = muted;
    ctx.font = '400 22px "Plex Body"';
    wrapText(ctx, lastCalc.ratio.toFixed(1) + 'x career earning uplift after rent, tax and cost of living, vs ' + DATA.cities[state.city].label, 90, 565, W-180, 30);

    ctx.strokeStyle = dark ? 'rgba(237,239,231,0.15)' : 'rgba(10,15,30,0.12)';
    ctx.beginPath(); ctx.moveTo(90,630); ctx.lineTo(W-90,630); ctx.stroke();

    ctx.fillStyle = muted; ctx.font = '600 18px "Plex Data"';
    ctx.fillText('NET PAY · ' + DATA.cities[state.city].label.toUpperCase(), 90, 680);
    ctx.fillStyle = ink; ctx.font = '600 30px "Plex Data"';
    ctx.fillText('₦' + fmt(lastCalc.y0.nairaNet), 90, 720);

    ctx.fillStyle = muted; ctx.font = '600 18px "Plex Data"';
    ctx.fillText('NET PAY · ' + lastCalc.dest.label.toUpperCase() + ' (POST-GRAD)', 90, 780);
    ctx.fillStyle = ink; ctx.font = '600 30px "Plex Data"';
    ctx.fillText(money(lastCalc.destAtGrad.foreignNetLocal, lastCalc.dest.symbol, lastCalc.dest.suffix), 90, 820);

    ctx.fillStyle = accent;
    for(var i=0;i<5;i++){ ctx.fillStyle = i<lastCalc.dest.visa ? accent : (dark? '#2A3352':'#DEE2D6'); roundRect(ctx, 90+i*40, 870, 32, 14, 4); ctx.fill(); }
    ctx.fillStyle = muted; ctx.font = '500 18px "Plex Body"';
    ctx.fillText('Study visa difficulty: ' + lastCalc.dest.visa + '/5', 90, 915);

    ctx.strokeStyle = dark ? 'rgba(237,239,231,0.15)' : 'rgba(10,15,30,0.12)';
    ctx.beginPath(); ctx.moveTo(90,960); ctx.lineTo(W-90,960); ctx.stroke();

    ctx.fillStyle = muted; ctx.font = '400 20px "Plex Body"';
    wrapText(ctx, 'A Master\'s at one of TGM\'s partner universities can get you there in ' + lastCalc.dest.studyMonths + '.', 90, 1010, W-180, 28);

    ctx.fillStyle = accent; ctx.font = '600 22px "Plex Data"';
    ctx.fillText('tgmeducation.com', 90, 1230);
    ctx.fillStyle = muted; ctx.font = '400 16px "Plex Body"';
    ctx.fillText('Illustrative benchmark data — not financial or immigration advice.', 90, 1270);
  }
  function roundRect(ctx,x,y,w,h,r){
    ctx.beginPath();
    ctx.moveTo(x+r,y); ctx.arcTo(x+w,y,x+w,y+h,r); ctx.arcTo(x+w,y+h,x,y+h,r); ctx.arcTo(x,y+h,x,y,r); ctx.arcTo(x,y,x+w,y,r); ctx.closePath();
  }
  function wrapText(ctx, text, x, y, maxWidth, lineHeight){
    var words = text.split(' '); var line=''; var yy=y;
    for(var n=0;n<words.length;n++){
      var test = line + words[n] + ' ';
      if(ctx.measureText(test).width > maxWidth && n>0){ ctx.fillText(line, x, yy); line = words[n]+' '; yy += lineHeight; }
      else{ line = test; }
    }
    ctx.fillText(line, x, yy);
  }

})();
