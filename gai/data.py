"""Labelled grievance dataset generator. Each template = (category, priority, subject, body).
Templates are split train/test BY TEMPLATE, so the test set contains phrasings the model never saw."""
import random
PLACES = ["Sector 7","Rampur","Civil Lines","Gandhi Nagar","Kakadeo","Ward 12","Shivpur","Mall Road","Barra","Naubasta","Panki","Kidwai Nagar","Juhi","Govind Nagar","Ashok Nagar"]
E, H, W, C, L, S, R, D, F, X = ("Emergency & Safety","Health","Water & Electricity","Corruption & Misconduct","Legal / Court / RTI","Welfare & Pension","Roads & Infrastructure","Education","Feedback & Suggestions","Spam / Irrelevant")
T = [
 (E,"Critical","Flood water entering houses","Flood water has entered homes in {place}. {n} families are stranded, please send rescue boats immediately."),
 (E,"Critical","Fire near {place} market","A fire broke out near {place} market. People are trapped and some are injured, send the fire brigade urgently."),
 (E,"Critical","Wall collapsed","A wall has collapsed in {place}. Several people are under the debris. Emergency help is needed now."),
 (E,"Critical","Major road accident","Major road accident near {place}. Many people are injured and bleeding, no ambulance has arrived."),
 (E,"Critical","Gas leak in locality","There is a strong gas leak in {place}, children are fainting. Please evacuate the area immediately."),
 (E,"Critical","बाढ़ का पानी घरों में","{place} में बाढ़ का पानी घरों में घुस गया है। {n} परिवार फंसे हैं, तुरंत मदद भेजें।"),
 (E,"Critical","Threat to my family","A group is threatening to attack my family in {place}. We fear for our lives, please send police tonight."),
 (H,"Critical","Oxygen shortage at hospital","Oxygen cylinders at {place} hospital will finish in a few hours. Ventilator patients are at risk."),
 (H,"Critical","My father cannot breathe","My father is gasping and cannot breathe properly, no doctor is available at the {place} health centre."),
 (H,"High","Dengue cases rising","Many cases of dengue have been reported in {place} for the past {d} days and no fogging has been done."),
 (H,"High","Medicines unavailable","The {place} dispensary has had no medicines for {d} days. Elderly patients are suffering."),
 (H,"Medium","Doctor absent at clinic","The doctor at {place} clinic is often absent and we wait long hours for a routine checkup."),
 (H,"High","अस्पताल में दवा नहीं","{place} के अस्पताल में {d} दिन से दवा नहीं है, मरीज परेशान हैं।"),
 (W,"High","No drinking water","We have had no water supply in {place} for {d} days. Residents are suffering badly."),
 (W,"High","Contaminated water","Water in {place} is dirty and smells, many people have fallen ill after drinking it."),
 (W,"Medium","Frequent power cuts","Power cuts happen daily for a few hours in {place}, please look into it."),
 (W,"High","बिजली नहीं है","हमारे गांव {place} में {d} दिन से बिजली नहीं है, ट्रांसफार्मर खराब है।"),
 (W,"Medium","Low water pressure","Water pressure in {place} is very low in the mornings, please check the pipeline."),
 (C,"High","Officer demanding bribe","The clerk at {place} office is demanding Rs {n} to process my file. This is corruption."),
 (C,"High","Fake bills in road work","The contractor submitted fake bills for work never done in {place}, officials are taking a cut."),
 (C,"High","Harassment by official","An official is harassing me and asking for money to clear my certificate."),
 (C,"High","रिश्वत की मांग","{place} कार्यालय में काम के लिए रिश्वत मांगी जा रही है।"),
 (L,"Critical","Court order compliance","The High Court order from last month has not been complied with. Contempt hearing is in {d} days."),
 (L,"High","RTI reply pending","My RTI application is pending beyond the legal time limit and the appeal deadline is approaching."),
 (L,"High","Legal notice received","Please find attached a legal notice against the department, reply required within {d} days."),
 (L,"High","Tribunal hearing next week","A tribunal hearing is scheduled next week and the department record is needed."),
 (S,"High","Pension not received","I am a widow and my pension has not come for {d} months. I wrote earlier but nobody replied."),
 (S,"High","Ration not given","My ration is not being given at the shop for the last {d} months, my children sleep hungry."),
 (S,"Medium","Scholarship delay","My scholarship for this year has not been credited yet."),
 (S,"Medium","Housing scheme status","Kindly tell me the status of my housing scheme application submitted last year."),
 (S,"High","पेंशन नहीं मिली","मैं विधवा हूँ और मुझे {d} महीने से पेंशन नहीं मिली है।"),
 (R,"Medium","Pothole on road","There is a big pothole on the main road near {place}, please repair it."),
 (R,"Medium","Garbage not collected","Garbage has not been collected in {place} for several days and it smells."),
 (R,"Low","Streetlight not working","One streetlight near my house in {place} is not working."),
 (R,"Medium","Encroachment on footpath","Shopkeepers have blocked the footpath in {place}."),
 (R,"High","Cracks in bridge","Large cracks have appeared in the bridge near {place}, heavy vehicles still pass over it."),
 (D,"Medium","Teacher vacancies","The government school in {place} has no maths teacher during the exam season."),
 (D,"Low","Admission query","What is the last date for admission in the government college?"),
 (D,"Medium","School roof leaking","The school roof in {place} leaks and children sit in the rain."),
 (D,"High","Poor mid-day meal","Children found insects in the mid-day meal at {place} school and several fell sick."),
 (F,"Low","Thank you","Thank you for the quick repair work in {place}. We appreciate the officials."),
 (F,"Low","Suggestion for park","I suggest adding more benches and a small library in the {place} park."),
 (F,"Low","Invitation","You are invited to our annual cultural programme at {place}."),
 (F,"Low","Congratulations","Congratulations on the successful health camp in {place}!"),
 (F,"Low","धन्यवाद","{place} में सड़क बनवाने के लिए धन्यवाद, बहुत अच्छा काम।"),
 (X,"Low","You won a lottery","Click here to claim your free gift, limited offer, buy now!"),
 (X,"Low","Crypto investment","Earn guaranteed returns with crypto, a loan offer is also available, click the link."),
 (X,"Low","Cheap pills","Buy cheap medicines online without prescription, free delivery."),
 (X,"Low","Weekly newsletter","Top deals this week. Unsubscribe here."),
 (X,"Low","Special promotion","Limited offer on watches, click here to buy now."),
]
GREET = ["", "Respected Sir, ", "Dear Sir/Madam, ", "Sir, ", "आदरणीय महोदय, "]
CLOSE = ["", "\nRegards", "\nThanks and regards", "\nकृपया ध्यान दें।"]

def build(per_template=30, seed=7):
    rng = random.Random(seed); rows = []; seen = {}
    for tid, (cat, pri, subj, body) in enumerate(T):
        i = seen[cat] = seen.get(cat, -1) + 1
        test = (i % 3 == 2)                       # every 3rd template of a category is held out
        for _ in range(per_template):
            f = dict(place=rng.choice(PLACES), n=rng.choice([20,50,120,200,350]), d=rng.choice([2,3,5,10,15,30,60]))
            s = subj.format(**f); b = rng.choice(GREET) + body.format(**f) + rng.choice(CLOSE)
            if rng.random() < .15: s = "URGENT: " + s      # random urgency words on ANY class: defeats keyword gaming
            rows.append(dict(subject=s, body=b, category=cat, priority=pri, test=test, tid=tid))
    return rows
