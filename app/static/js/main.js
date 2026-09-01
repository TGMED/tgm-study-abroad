(function(){

  // ---------------------------------------------------------------------
  // Sourced assumption data (replaces the earlier flat/guessed constants).
  // Every salary/tax/rent figure below was pulled from official statistics
  // bodies, tax authorities, or (where no government occupation-level data
  // exists) a named, cited market survey -- research pass dated Aug 2026.
  // Figures marked "proxy"/"best estimate" in the per-destination comments
  // below are the ones no official source directly covers; everything else
  // is a real published number, not a guess. This is still a snapshot, not
  // a live feed -- refresh it periodically (tax bands and minimum wages in
  // particular change yearly).
  // ---------------------------------------------------------------------
  var WEEKS_PER_MONTH = 52 / 12;

  var DATA = {
    cities: {
      // Nigeria has no official (NBS) rent index -- these are directional
      // mid-range 1-bedroom figures from real-estate market aggregators,
      // not a single authoritative statistical series. Source: Lagos from
      // The Africanvestor (2026 rent update); Abuja/Port Harcourt from
      // GidiStay's 2026 city rent guide. Refresh quarterly given ~25-40%
      // y/y rent inflation reported amid naira volatility.
      lagos:        { label:"Lagos",         code:"LOS", rent:185000 },
      abuja:        { label:"Abuja",         code:"ABV", rent:150000 },
      portharcourt: { label:"Port Harcourt", code:"PHC", rent:140000 }
    },

    // No official NBS "average wage growth" series exists; private-sector
    // HR-platform estimates cluster around 5-8% nominal/year (Trading
    // Economics/NBS minimum-wage data + HR salary-survey commentary), well
    // below the ~15.9% CPI inflation NBS reported for June 2026 -- i.e.
    // real wages have been falling. 0.06 is the midpoint of that nominal
    // range, kept nominal (not inflation-adjusted) to match how every
    // destination's growth rate below is also modeled in nominal terms.
    nigeriaGrowth: 0.06,

    professions: [
      { id:"swe",     label:"Software Engineer" },
      { id:"nurse",   label:"Registered Nurse" },
      { id:"acct",    label:"Accountant" },
      { id:"teacher", label:"Secondary School Teacher" },
      { id:"civeng",  label:"Civil Engineer" },
      { id:"analyst", label:"Data Analyst" },
      { id:"doctor",  label:"Medical Doctor" },
      { id:"mktg",    label:"Marketing Manager" },
      { id:"design",  label:"Graphic Designer" },
      { id:"mecheng", label:"Mechanical Engineer" },
      { id:"pharm",   label:"Pharmacist" },
      { id:"lawyer",  label:"Lawyer" }
    ],

    // Each destination now carries its own real occupation salary table
    // (monthly, local currency) instead of scaling a single UK figure by a
    // guessed cross-country "factor". taxBands are cumulative marginal-rate
    // brackets in ANNUAL local currency (Canada and Ireland are pre-merged
    // federal/provincial or income-tax/USC tables); payroll entries are
    // additional flat-rate contributions (NI, CPP/EI, German social
    // insurance, ZUS, PRSI) applied only between their floor/ceiling.
    destinations: [
      {
        id:"uk", label:"United Kingdom", flag:"🇬🇧", currency:"GBP", symbol:"£", suffix:false,
        rate:2000, rent:1700,
        // Study-phase housing (not the full 1-bed above): shared/HMO room
        // rent, SpareRoom Rental Index, London, ~£980-995/month (2025) --
        // more representative of a part-time-working student's budget than
        // the halls-of-residence average (~£1,278/month, Unipol/HEPI).
        studyRent:1000,
        growth:0.042, visa:3,
        visaNote:"Student Route — well-trodden for Nigerians via licensed university sponsors; Graduate Route gives 2 years post-study work.",
        studyMonths:"12–15 months", studyDuration:1.1,
        // Salaries: National Careers Service (gov.uk) job-profile bands,
        // midpoint of stated range, except Nurse (NHS Band 5 entry, NHS
        // Employers Agenda for Change 2025) and Doctor (FY1 basic, BMA pay
        // scale 2025/26) which use the precise scale point. Monthly = /12.
        salaries: { swe:4375, nurse:2587, acct:3750, teacher:2743, civeng:3833, analyst:3875, doctor:3236, mktg:3958, design:2708, mecheng:3667, pharm:3429, lawyer:4583 },
        // Tax: Personal Allowance/Basic/Higher/Additional rate bands,
        // gov.uk "Income Tax rates and Personal Allowances" 2025/26
        // (ignores the >£100k allowance taper -- none of the salaries
        // above reach it). Payroll: employee Class 1 National Insurance,
        // gov.uk "National Insurance rates and categories" 2025/26.
        taxBands:[[12570,0],[50270,0.20],[125140,0.40],[Infinity,0.45]],
        payroll:[{rate:0.08,floor:12570,ceiling:50270},{rate:0.02,floor:50270,ceiling:Infinity}],
        // Student Route: 20 hrs/week during term (gov.uk Student visa
        // "Working" rules). Minimum wage: National Living Wage 21+,
        // £12.21/hr from 1 Apr 2025 (gov.uk).
        weeklyWorkHours:20, minWage:12.21
      },
      {
        id:"canada", label:"Canada", flag:"🇨🇦", currency:"CAD", symbol:"CA$", suffix:false,
        rate:1050, rent:2073,
        // Study-phase housing: shared accommodation, Rentals.ca 2025 Toronto
        // data (~$1,200/mo). Only ~7-9% of Toronto students actually live in
        // (capacity-limited) on-campus residence, per Globe and Mail
        // reporting on the city's off-campus housing market -- shared
        // housing is the realistic modal outcome, not the exception.
        studyRent:1200,
        growth:0.025, visa:4,
        visaNote:"Study Permit — proof-of-funds scrutiny and 2024 intake caps have raised refusal rates for Nigerian applicants.",
        studyMonths:"16–24 months", studyDuration:1.65,
        // Salaries: Job Bank Canada wage reports (StatCan Labour Force
        // Survey basis), Toronto Region median hourly x 1,950 hrs/yr where
        // available, else Ontario-wide; Doctor is Job Bank's own annual
        // family-physician figure; Lawyer uses a first-year-associate
        // market survey (NALP Canada/Canadian Lawyer, not government data)
        // since the province-wide median blends all experience levels.
        salaries: { swe:9183, nurse:6596, acct:6642, teacher:7719, civeng:7813, analyst:7225, doctor:19479, mktg:9333, design:5313, mecheng:7542, pharm:8750, lawyer:10833 },
        // Tax: federal (CRA, 2026 bands incl. basic personal amount) +
        // Ontario provincial (2025 bands, ON 2026 not yet published) tax
        // pre-merged into one combined marginal-rate table. Payroll: CPP
        // 5.95% (+CPP2 4% on the next band) and EI 1.64%, both capped --
        // Canada.ca "Payroll Deductions" / KPMG's rate summary, 2025/26.
        taxBands:[[12747,0],[16452,0.0505],[52886,0.1905],[58523,0.2315],[105775,0.2965],[117045,0.3166],[150000,0.3716],[181440,0.3816],[220000,0.4116],[258482,0.4216],[Infinity,0.4616]],
        payroll:[{rate:0.0595,floor:3500,ceiling:71300},{rate:0.04,floor:71300,ceiling:81200},{rate:0.0164,floor:0,ceiling:65700}],
        // Off-campus work cap: 24 hrs/week during term, effective Nov 2024
        // (IRCC). Minimum wage: Ontario general rate $17.60/hr from 1 Oct
        // 2025 (Ontario.ca).
        weeklyWorkHours:24, minWage:17.60
      },
      {
        id:"germany", label:"Germany", flag:"🇩🇪", currency:"EUR", symbol:"€", suffix:false,
        rate:1650, rent:860,
        // Study-phase housing: weighted blend of Studierendenwerk dorm rent
        // (€337/mo, Berlin) and shared-flat/WG rent (~€600/mo, 2025), using
        // IW Köln's finding that 46.2% of international students in Germany
        // live in dorms vs only 13.1% of domestic students -- the one
        // destination where a real usage split, not just a price, was found.
        studyRent:480,
        growth:0.042, visa:3,
        visaNote:"National student visa — blocked account (~€11,900/yr) and B1/B2 German are the main hurdles, process is predictable.",
        studyMonths:"18–24 months", studyDuration:1.75,
        // Salaries: Entgeltatlas (Bundesagentur für Arbeit federal salary
        // explorer), national median except Doctor/Pharmacist which use
        // Berlin-specific figures; Data Analyst uses the nearest matching
        // occupation code (proxy, flagged); Lawyer's Entgeltatlas entry is
        // censored above the contribution ceiling, so uses a market-range
        // midpoint instead (not itself government data).
        salaries: { swe:6083, nurse:4329, acct:3438, teacher:5450, civeng:5500, analyst:6475, doctor:6646, mktg:5014, design:3525, mecheng:5946, pharm:4558, lawyer:4167 },
        // Tax: piecewise approximation of Germany's continuous §32a EStG
        // formula (BMF Lohnsteuer-Handbuch 2026 zone boundaries) -- a true
        // per-euro formula would be more precise but this tracks the same
        // zone thresholds/average marginal rates. Payroll: combined
        // employee social-insurance share (pension+health+unemployment+
        // long-term care) ≈20.9% of gross, per BMAS 2025 contribution
        // rates, applied uncapped (all salaries above are below the real
        // contribution ceiling).
        taxBands:[[12348,0],[17799,0.19],[69878,0.33],[277825,0.42],[Infinity,0.45]],
        payroll:[{rate:0.209,floor:0,ceiling:Infinity}],
        // Student work cap: 140 full days/year, ≈20 hrs/week during term
        // (Fachkräfteeinwanderungsgesetz, effective Mar 2024). Minimum
        // wage: €13.90/hr from 1 Jan 2026 (BMAS/Mindestlohnkommission).
        weeklyWorkHours:20, minWage:13.90
      },
      {
        id:"poland", label:"Poland", flag:"🇵🇱", currency:"PLN", symbol:"zł", suffix:true,
        rate:380, rent:5300,
        // Study-phase housing: blended estimate weighted toward university
        // dormitory (akademik) rates (~400-800 PLN/mo across UW/WUT/SGH/
        // SGGW, ~650 PLN average), since dorms are the default cost-
        // conscious choice and are often prioritized for international
        // students -- no single official composite exists for this figure.
        studyRent:800,
        growth:0.091, visa:2,
        visaNote:"EU national student visa — lower financial threshold, decent approval rates, Schengen access.",
        studyMonths:"12 months", studyDuration:1.0,
        // Salaries: Sedlak & Sedlak's national salary survey (wynagrodzenia.pl),
        // national medians (no Warsaw-only breakdown exists per-occupation).
        // Teacher uses the statutory base rate only (real pay is typically
        // higher with allowances, not captured here); Data Analyst and
        // Mechanical Engineer use nearest-title proxies (flagged); Doctor
        // uses the Ministry of Health's resident-physician pay regulation.
        salaries: { swe:11900, nurse:8970, acct:7660, teacher:6211, civeng:9120, analyst:9750, doctor:11655, mktg:11250, design:7180, mecheng:7550, pharm:8800, lawyer:7360 },
        // Tax: PIT 12%/32% bands with a PLN 30,000/year tax-free amount
        // (applied as a PLN 3,600/year credit) — podatki.gov.pl, 2025/26.
        // Payroll: ZUS social insurance (~13.71%) + health insurance (9%),
        // both applied uncapped here as a simplification — zus.pl, 2025/26.
        taxBands:[[120000,0.12],[Infinity,0.32]], taxCredit:3600,
        payroll:[{rate:0.2271,floor:0,ceiling:Infinity}],
        // Non-EU degree students: 20 hrs/week during term, 40 hrs/week
        // during breaks, no separate work permit needed (Foreigners Act,
        // per 2025 immigration-law summaries). Minimum wage: PLN 31.40/hr
        // from 1 Jan 2026 (Dziennik Ustaw/gov.pl regulation).
        weeklyWorkHours:20, minWage:31.40
      },
      {
        id:"ireland", label:"Ireland", flag:"🇮🇪", currency:"EUR", symbol:"€", suffix:false,
        rate:1650, rent:1592,
        // Study-phase housing: purpose-built student accommodation (PBSA),
        // Cushman & Wakefield Irish Student Accommodation Review (~€1,100-
        // 1,150/mo) -- PBSA is structurally the more accessible option for
        // international students (short academic-term licences, no local
        // guarantor needed), vs. shared digs (~€750/mo) which typically
        // require in-person viewing and a local guarantor.
        studyRent:1100,
        growth:0.035, visa:3,
        visaNote:"Non-EEA student visa — tuition paid upfront plus proof of funds; Stamp 1G gives up to 2 years post-study work.",
        studyMonths:"12–16 months", studyDuration:1.15,
        // Salaries: Morgan McKinley Ireland Salary Guide 2026 (recruitment
        // survey, not government data — CSO doesn't publish occupation-
        // level earnings) except Nurse/Doctor, which use HSE's official
        // Consolidated Pay Scales; Civil/Mechanical Engineer use Engineers
        // Ireland's 2025 salary survey; Pharmacist is the weakest-sourced
        // entry (secondary aggregator of the HSE scale).
        salaries: { swe:5000, nurse:3181, acct:5417, teacher:3951, civeng:4583, analyst:4583, doctor:4844, mktg:6667, design:4167, mecheng:4375, pharm:4083, lawyer:5917 },
        // Tax: income tax 20%/40% bands + USC (Universal Social Charge)
        // bands pre-merged into one combined marginal-rate table — both
        // from Revenue.ie, 2025/26 (income tax bands unchanged in Budget
        // 2026). Ignores personal tax credits, which would lower the
        // effective rate somewhat at low incomes. Payroll: employee PRSI
        // Class A, flat 4.2% (gov.ie, 2025/26).
        taxBands:[[12012,0.205],[28700,0.22],[44000,0.23],[70044,0.43],[Infinity,0.48]],
        payroll:[{rate:0.042,floor:0,ceiling:Infinity}],
        // Stamp 2 non-EEA students: 20 hrs/week during term, 40 hrs/week
        // during official college holidays (citizensinformation.ie).
        // Minimum wage: €14.15/hr (age 20+) from 1 Jan 2026 (gov.ie).
        weeklyWorkHours:20, minWage:14.15
      }
    ]
  };

  // Progressive marginal-rate tax on ANNUAL income. `bands` is a list of
  // [upperThreshold, rate] pairs, contiguous from 0, last threshold Infinity.
  function marginalTax(annual, bands){
    var tax = 0, prev = 0;
    for(var i=0; i<bands.length; i++){
      var upper = bands[i][0], rate = bands[i][1];
      if(annual > prev){ tax += (Math.min(annual, upper) - prev) * rate; }
      prev = upper;
      if(annual <= upper) break;
    }
    return tax;
  }
  // A flat-rate contribution (NI/CPP/ZUS/PRSI-style) applied only to the
  // slice of annual income between floor and ceiling.
  function bandedContribution(annual, rate, floor, ceiling){
    var amt = Math.min(annual, ceiling) - floor;
    return amt > 0 ? amt * rate : 0;
  }
  function destAnnualDeduction(dest, annual){
    var tax = Math.max(0, marginalTax(annual, dest.taxBands) - (dest.taxCredit || 0));
    var payroll = 0;
    (dest.payroll || []).forEach(function(p){ payroll += bandedContribution(annual, p.rate, p.floor, p.ceiling); });
    return tax + payroll;
  }
  // The "Monthly salary" field is what people actually type when asked
  // this casually -- their take-home pay, already net of tax -- not a
  // gross figure. Taxing it again would double-count PAYE. So Nigeria PAYE
  // isn't applied on this side at all; the entered figure is deducted only
  // for rent, the one expense "take-home pay" doesn't already net out.
  //
  // Cap: cityData.rent is a real mid-range 1-bed market figure, but charging
  // it flat regardless of income means a modest earner's net pay gets
  // crushed by a rent they'd never actually take on -- nobody earning
  // ₦150,000/month rents a ₦150,000/month Abuja apartment. Capping at 40% of
  // take-home keeps the sourced figure as the ceiling for anyone who can
  // plausibly afford it, while scaling down realistically below that.
  var NIGERIA_RENT_AFFORDABILITY_CAP = 0.40;

  function nigeriaTakeHomeAfterRent(monthlyNet, cityResolved, spouse, children){
    var householdMult = 1 + (spouse?0.4:0) + children*0.25;
    var rentBase = Math.min(cityResolved.rent, monthlyNet * NIGERIA_RENT_AFFORDABILITY_CAP);
    var rent = rentBase * householdMult;
    var childCost = children * rentBase * 0.15;
    return monthlyNet - rent - childCost;
  }

  var state = { profession:null, salary:null, destination:null, spouse:false, children:0, familyOpen:false, calculated:false };

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

  // ---------- populate cities ----------
  var cityList = $('cities');
  Object.keys(DATA.cities).forEach(function(key){
    var opt = document.createElement('option');
    opt.value = DATA.cities[key].label;
    cityList.appendChild(opt);
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

  // Profession and city are free text -- not limited to the sourced lists.
  // A typed value that matches a known label (case-insensitively) gets the
  // real sourced figure; anything else still calculates, using a clearly-
  // labeled average/fallback instead of either refusing input or silently
  // presenting a guess as if it were sourced data (see estimateNote in
  // runCalculation).
  function resolveProfession(text){
    var norm = (text||'').trim().toLowerCase();
    if(!norm) return null;
    for(var i=0;i<DATA.professions.length;i++){
      if(DATA.professions[i].label.toLowerCase()===norm) return { id: DATA.professions[i].id, label: DATA.professions[i].label, sourced:true };
    }
    return { id: null, label: (text||'').trim(), sourced:false };
  }

  // Average of the 12 sourced salaries for a destination, used as the
  // fallback baseline when the typed profession has no specific sourced
  // figure -- a generic "professional" anchor rather than a made-up number
  // for that specific unmatched title.
  function destAverageSalary(dest){
    var vals = Object.keys(dest.salaries).map(function(k){ return dest.salaries[k]; });
    return vals.reduce(function(a,b){ return a+b; }, 0) / vals.length;
  }

  function resolveCity(text){
    var norm = (text||'').trim().toLowerCase();
    if(!norm) return null;
    for(var key in DATA.cities){
      if(DATA.cities[key].label.toLowerCase()===norm){
        var c = DATA.cities[key];
        return { label:c.label, code:c.code, rent:c.rent, sourced:true };
      }
    }
    var typed = (text||'').trim();
    var rents = Object.keys(DATA.cities).map(function(k){ return DATA.cities[k].rent; });
    var avgRent = rents.reduce(function(a,b){ return a+b; }, 0) / rents.length;
    return { label:typed, code:typed.slice(0,3).toUpperCase(), rent:avgRent, sourced:false };
  }

  function findDestination(id){
    for(var i=0;i<DATA.destinations.length;i++){ if(DATA.destinations[i].id===id) return DATA.destinations[i]; }
    return null;
  }

  function updateCalcButton(){
    var salaryVal = parseFloat(($('salary').value||'').replace(/,/g,''));
    var profText = ($('profession').value||'').trim();
    var cityText = ($('city').value||'').trim();
    var ok = profText && salaryVal > 0 && cityText && state.destination;
    $('calcBtn').disabled = !ok;
  }

  $('profession').addEventListener('input', updateCalcButton);
  $('salary').addEventListener('input', function(){
    var v = this.value.replace(/[^0-9]/g,'');
    this.value = v ? Number(v).toLocaleString('en-US') : '';
    updateCalcButton();
    if(state.calculated) runCalculation();
  });
  $('city').addEventListener('input', function(){ updateCalcButton(); if(state.calculated) runCalculation(); });

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
  // Nigeria "without further study" trajectory (today's role, growing at
  // DATA.nigeriaGrowth). Foreign figures used to be computed here too but
  // were dead code -- computeDestNet below is what the chart actually uses
  // for the destination side.
  function computeForYear(cityResolved, spouse, children, year){
    var salaryInputNaira = parseFloat(($('salary').value||'0').replace(/,/g,''));
    var monthlyNet = salaryInputNaira * Math.pow(1+DATA.nigeriaGrowth, year);
    return { nairaNet: nigeriaTakeHomeAfterRent(monthlyNet, cityResolved, spouse, children) };
  }

  function computeDestNet(profession, dest, spouse, children, year){
    var householdMult = 1 + (spouse?0.4:0) + children*0.25;
    // Unmatched profession (typed something outside the 12 sourced titles):
    // fall back to this destination's average sourced salary as a generic
    // professional baseline, rather than fabricating a specific number for
    // that title -- runCalculation flags this to the user via estimateNote.
    var qualifiedMonthly = profession.id ? dest.salaries[profession.id] : destAverageSalary(dest);
    var studying = year < dest.studyDuration;

    // A student on part-time minimum-wage income doesn't rent the same
    // solo 1-bed a working graduate does -- they're in halls/dorms or
    // shared housing (dest.studyRent, sourced separately per destination),
    // not the full market dest.rent figure used once qualified/working.
    var rentBase = studying ? dest.studyRent : dest.rent;
    var rent = rentBase * householdMult;
    var childCost = children * rentBase * 0.3;

    // While studying, income is capped at what the destination's own
    // student-visa work-hour limit and minimum wage actually allow --
    // hours/week x local minimum wage x weeks/month -- not an arbitrary
    // fraction of the qualified salary. Full qualified pay only starts at
    // graduation, which is what turns the trajectory into a real staged
    // path (low during study, a step up at graduation, growth from there).
    var localGross = studying
      ? dest.weeklyWorkHours * dest.minWage * WEEKS_PER_MONTH
      : qualifiedMonthly * Math.pow(1+dest.growth, year - dest.studyDuration);

    var deduction = destAnnualDeduction(dest, localGross * 12) / 12;
    var netLocal = localGross - deduction - rent - childCost;
    return { foreignNetLocal:netLocal, foreignNetNGN:netLocal*dest.rate, phase: studying ? 'study' : 'working' };
  }

  // Many students plan to return to Nigeria after finishing the Master's
  // rather than stay abroad. No Nigeria-specific study of the wage premium
  // for returnees with a foreign postgraduate qualification exists; the
  // closest available proxy is Jackline Wahba's IZA World of Labor review,
  // which finds Egyptian university-graduate returnees earn ~24% more than
  // non-migrant graduates (West African returnees see a premium mainly when
  // returning from an OECD country, consistent with our UK/Canada/Germany/
  // Ireland destinations). 1.20 (a 20% premium) sits near that figure --
  // flagged explicitly as a non-Nigeria-specific proxy, not a benchmarked
  // Nigerian number.
  var RETURNEE_QUALIFICATION_PREMIUM = 1.20;

  function computeNigeriaReturneeNet(cityResolved, spouse, children, studyDuration, year){
    var salaryInputNaira = parseFloat(($('salary').value||'0').replace(/,/g,''));
    var netAtReturn = salaryInputNaira * Math.pow(1+DATA.nigeriaGrowth, studyDuration) * RETURNEE_QUALIFICATION_PREMIUM;
    var yearsSinceReturn = Math.max(0, year - studyDuration);
    var monthlyNet = netAtReturn * Math.pow(1+DATA.nigeriaGrowth, yearsSinceReturn);
    return { nairaNet: nigeriaTakeHomeAfterRent(monthlyNet, cityResolved, spouse, children) };
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
    var prof = resolveProfession($('profession').value);
    var cityResolved = resolveCity($('city').value);
    var dest = findDestination(state.destination);
    if(!prof || !cityResolved || !dest) return;
    state.profession = prof; state.calculated = true;

    var cityLabel = cityResolved.label;
    var y0 = computeForYear(cityResolved, state.spouse, state.children, 0);
    // The headline ROI compares today's actual Nigeria pay against the
    // destination salary you'd actually earn once qualified (i.e. right at
    // graduation) -- not an immediate foreign salary, since that's not real.
    var destAtGrad = computeDestNet(prof, dest, state.spouse, state.children, dest.studyDuration);
    var ratio = destAtGrad.foreignNetNGN / y0.nairaNet;
    var score = scoreFromRatio(ratio);
    var v = verdictFor(ratio);

    // Profession/city outside the sourced lists still calculate (using the
    // fallback baselines in computeDestNet/resolveCity) -- but the user
    // should see that a specific figure was substituted, not just get a
    // number that looks as precisely sourced as everything else.
    var estimateNotes = [];
    if(!prof.sourced) estimateNotes.push('"' + prof.label + '" isn\'t one of our sourced occupations — using ' + dest.label + '\'s average professional salary instead.');
    if(!cityResolved.sourced) estimateNotes.push('"' + cityResolved.label + '" isn\'t one of our sourced Nigerian cities — using the average of Lagos/Abuja/Port Harcourt rent instead.');
    $('estimateNote').textContent = estimateNotes.join(' ');
    $('estimateNote').classList.toggle('show', estimateNotes.length > 0);

    $('bpFrom').textContent = cityResolved.code;
    $('bpTo').textContent = dest.id === 'uk' ? 'LON' : dest.id==='canada' ? 'YYZ' : dest.id==='germany' ? 'BER' : dest.id==='poland' ? 'WAW' : 'DUB';
    $('bpProfession').textContent = ' · ' + prof.label;
    $('bpVerdict').innerHTML = score + '<span style="font-size:0.4em; color:var(--text-muted);">/100</span>';
    $('bpSub').textContent = v.text + ' — ' + v.sub;
    $('bpNairaLabel').textContent = 'Left after rent, ' + cityLabel;
    $('bpNaira').textContent = money(y0.nairaNet, '₦', false) + '/mo';
    $('bpForeignLabel').textContent = 'Left after rent, ' + dest.label;
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
    var nigeriaSeries = years.map(function(y){ return computeForYear(cityResolved, state.spouse, state.children, y).nairaNet; });
    var destSeries = years.map(function(y){ return computeDestNet(prof, dest, state.spouse, state.children, y).foreignNetNGN; });
    renderChart(years, nigeriaSeries, destSeries, 'Without further study', 'With a Master\'s abroad', dest.studyDuration);
    renderTable(years, nigeriaSeries, destSeries);

    var destDuringStudy = computeDestNet(prof, dest, state.spouse, state.children, 0);
    // Alternative path: return to Nigeria after graduating instead of staying
    // abroad. Uses the qualification-premium model above, not the "stay
    // abroad" destination figures.
    var returneeAtGrad = computeNigeriaReturneeNet(cityResolved, state.spouse, state.children, dest.studyDuration, dest.studyDuration);
    var returneeYear5 = computeNigeriaReturneeNet(cityResolved, state.spouse, state.children, dest.studyDuration, 5);
    var enteredTakeHome = parseFloat(($('salary').value||'0').replace(/,/g,'')) || 0;
    renderPathBreakdown(prof, dest, cityLabel, enteredTakeHome, y0, destDuringStudy, destAtGrad, ratio, v,
      nigeriaSeries[nigeriaSeries.length-1], destSeries[destSeries.length-1], returneeAtGrad, returneeYear5);

    $('results').classList.add('show');
    lastCalc = { prof:prof, dest:dest, city:cityResolved, ratio:ratio, score:score, v:v, y0:y0, destAtGrad:destAtGrad };
  }

  // ---------- plain-English breakdown ----------
  function renderPathBreakdown(prof, dest, cityLabel, enteredTakeHome, y0, destDuringStudy, destAtGrad, ratio, v, finalNigeriaNGN, finalDestNGN, returneeAtGrad, returneeYear5){
    var safeRatio = isFinite(ratio) ? ratio : 0;
    var returneeRatio = returneeAtGrad.nairaNet / y0.nairaNet;
    var interpretation =
      'Right now, as a ' + prof.label + ' in ' + cityLabel + ', your take-home pay is ' + money(enteredTakeHome,'₦',false) +
      '/month — after modeled rent, that leaves about ' + money(y0.nairaNet,'₦',false) + '/month, which is what the comparison below is based on. ' +
      'A Master\'s in ' + dest.label + ' takes about ' + dest.studyMonths + ' — during that time, expect only modest part-time income, around ' +
      money(destDuringStudy.foreignNetLocal, dest.symbol, dest.suffix) + '/month. ' +
      'Once you graduate, a ' + prof.label + ' role there could pay around ' + money(destAtGrad.foreignNetLocal, dest.symbol, dest.suffix) +
      '/month — about ' + Math.max(safeRatio,0).toFixed(1) + 'x what you take home after rent now — growing toward roughly ' + money(finalDestNGN,'₦',false) +
      '/month (₦-equivalent) by year 5. ' + v.sub + ' ' +
      'And if you come back to Nigeria after the Master\'s instead of staying in ' + dest.label + ', the qualification itself is usually worth a real premium here too — realistically around ' +
      money(returneeAtGrad.nairaNet,'₦',false) + '/month in ' + cityLabel + ' right after you return (about ' + Math.max(returneeRatio,0).toFixed(1) + 'x what you take home after rent now), ' +
      'growing toward roughly ' + money(returneeYear5.nairaNet,'₦',false) + '/month by year 5 — so the degree still pays off even if you don\'t stay abroad.';
    $('pathInterpretation').textContent = interpretation;

    var steps = [
      { label: 'Now', detail: prof.label + ' in ' + cityLabel + ', take-home ' + money(enteredTakeHome,'₦',false) + '/mo (about ' + money(y0.nairaNet,'₦',false) + '/mo after rent).' },
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
    params.set('city', $('city').value);
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
    var city = params.get('city'); if(city){ $('city').value = city; }
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
      city: ($('city').value || '').trim(),
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
    ctx.fillText((lastCalc.prof.label + ' · ' + lastCalc.city.label + ' → ' + lastCalc.dest.label).toUpperCase(), 90, 240);

    ctx.fillStyle = stamp;
    ctx.font = '600 128px "Plex Data"';
    ctx.fillText(lastCalc.score + '/100', 90, 400);
    ctx.fillStyle = ink;
    ctx.font = '900 42px "Fraunces Display"';
    wrapText(ctx, lastCalc.v.text, 90, 470, W-260, 48);

    ctx.fillStyle = muted;
    ctx.font = '400 22px "Plex Body"';
    wrapText(ctx, lastCalc.ratio.toFixed(1) + 'x career earning uplift after rent, tax and cost of living, vs ' + lastCalc.city.label, 90, 565, W-180, 30);

    ctx.strokeStyle = dark ? 'rgba(237,239,231,0.15)' : 'rgba(10,15,30,0.12)';
    ctx.beginPath(); ctx.moveTo(90,630); ctx.lineTo(W-90,630); ctx.stroke();

    ctx.fillStyle = muted; ctx.font = '600 18px "Plex Data"';
    ctx.fillText('NET PAY · ' + lastCalc.city.label.toUpperCase(), 90, 680);
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
