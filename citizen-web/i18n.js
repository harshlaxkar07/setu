/* Setu citizen UI strings (enhancements design D7).
 *
 * Every visible string lives here in Hindi (hi), Marathi (mr) and English
 * (en). The chosen language is the primary line; unless it is English, an
 * English subtitle follows (citizen register: bilingual, Hindi-first).
 * `{name}` placeholders are filled from the vars passed to tr().
 */
"use strict";

const LANGS = {
  hi: { label: "हिंदी", speech: "hi-IN", htmlLang: "hi" },
  mr: { label: "मराठी", speech: "mr-IN", htmlLang: "mr" },
  en: { label: "English", speech: "en-IN", htmlLang: "en" },
};

const STRINGS = {
  header_title: {
    hi: "अपनी समस्या बताइए", mr: "तुमची समस्या सांगा", en: "Tell us about your problem" },
  anon: { hi: "गुमनाम", mr: "निनावी", en: "Anonymous" },
  welcome: {
    hi: "नमस्ते! पानी, सड़क, बिजली या अस्पताल की समस्या हो तो माइक दबाकर बोलिए, या नीचे लिखिए। आपका नाम या फ़ोन नंबर नहीं पूछा जाएगा।",
    mr: "नमस्कार! पाणी, रस्ता, वीज किंवा दवाखान्याची समस्या असेल तर माइक दाबून बोला, किंवा खाली लिहा. तुमचे नाव किंवा फोन नंबर विचारला जाणार नाही.",
    en: "Namaste! Press and hold the mic to describe a water, road, electricity or health problem — or type below. We never ask your name or phone number." },
  topic_water: { hi: "पानी", mr: "पाणी", en: "Water" },
  topic_road: { hi: "सड़क", mr: "रस्ता", en: "Road" },
  topic_health: { hi: "अस्पताल", mr: "दवाखाना", en: "Health" },
  topic_power: { hi: "बिजली", mr: "वीज", en: "Electricity" },
  prefix_water: { hi: "पानी की समस्या: ", mr: "पाण्याची समस्या: ", en: "Water problem: " },
  prefix_road: { hi: "सड़क की समस्या: ", mr: "रस्त्याची समस्या: ", en: "Road problem: " },
  prefix_health: { hi: "अस्पताल / इलाज की समस्या: ", mr: "दवाखाना / उपचाराची समस्या: ", en: "Health problem: " },
  prefix_power: { hi: "बिजली की समस्या: ", mr: "विजेची समस्या: ", en: "Electricity problem: " },
  placeholder: { hi: "यहाँ लिखिए…", mr: "इथे लिहा…", en: "Type here…" },
  mic_hint: { hi: "बोलने के लिए माइक दबाकर रखें", mr: "बोलण्यासाठी माइक दाबून ठेवा", en: "Press and hold the mic to speak" },
  send_label: { hi: "भेजें", mr: "पाठवा", en: "Send" },
  mic_label: { hi: "दबाकर रखें और बोलें", mr: "दाबून ठेवा आणि बोला", en: "Press and hold to speak" },
  speak_label: { hi: "सुनिए", mr: "ऐका", en: "Listen" },

  sending: { hi: "भेजा जा रहा…", mr: "पाठवत आहे…", en: "sending…" },
  received: { hi: "मिल गया", mr: "मिळाले", en: "received" },
  recorded: { hi: "दर्ज", mr: "नोंद झाली", en: "recorded" },
  send_failed: {
    hi: "भेजा नहीं जा सका — कृपया दोबारा कोशिश करें।",
    mr: "पाठवता आले नाही — कृपया पुन्हा प्रयत्न करा.",
    en: "Could not send — please try again." },
  voice_failed: {
    hi: "आवाज़ भेजी नहीं जा सकी — कृपया दोबारा कोशिश करें।",
    mr: "आवाज पाठवता आला नाही — कृपया पुन्हा प्रयत्न करा.",
    en: "Could not send the voice note — please try again." },
  mic_denied: {
    hi: "माइक की अनुमति नहीं मिली, इसलिए आवाज़ से भेजना अभी संभव नहीं है। आप नीचे लिखकर अपनी बात भेज सकते हैं।",
    mr: "माइकची परवानगी मिळाली नाही, त्यामुळे आवाजाने पाठवता येणार नाही. तुम्ही खाली लिहून पाठवू शकता.",
    en: "Microphone permission was denied, so voice is unavailable. You can still type your message below." },
  hold_hint: {
    hi: "बोलने के लिए माइक बटन दबाकर रखें।",
    mr: "बोलताना माइक बटण दाबून ठेवा.",
    en: "Press and hold the mic button while you speak." },

  receipt_title: { hi: "आपकी बात दर्ज हो गई है ✓", mr: "तुमची तक्रार नोंदवली गेली ✓", en: "Your report is recorded ✓" },
  receipt_line: { hi: "हमने समझा: {cat}, {urg}", mr: "आम्हाला समजले: {cat}, {urg}", en: "We understood: {cat}, {urg}" },
  ai_chip: { hi: "✦ AI-सहायता से", mr: "✦ AI-सहाय्याने", en: "✦ AI-drafted" },
  retry_note: {
    hi: "आपकी बात सुरक्षित दर्ज है। सिस्टम इसे थोड़ी देर में दोबारा पढ़ेगा।",
    mr: "तुमची तक्रार सुरक्षित नोंदवली आहे. प्रणाली ती थोड्या वेळाने पुन्हा वाचेल.",
    en: "Your message is safely recorded; the system will retry processing it." },

  cat_water_infrastructure: { hi: "पानी की समस्या", mr: "पाण्याची समस्या", en: "water supply issue" },
  cat_road_infrastructure: { hi: "सड़क की समस्या", mr: "रस्त्याची समस्या", en: "road issue" },
  cat_healthcare: { hi: "स्वास्थ्य सेवा की समस्या", mr: "आरोग्य सेवेची समस्या", en: "health service issue" },
  cat_electricity: { hi: "बिजली की समस्या", mr: "विजेची समस्या", en: "electricity issue" },
  cat_sanitation: { hi: "सफ़ाई की समस्या", mr: "स्वच्छतेची समस्या", en: "sanitation issue" },
  cat_education: { hi: "शिक्षा की समस्या", mr: "शिक्षणाची समस्या", en: "education issue" },
  cat_transportation: { hi: "यातायात की समस्या", mr: "वाहतुकीची समस्या", en: "transport issue" },
  cat_digital_connectivity: { hi: "इंटरनेट/नेटवर्क की समस्या", mr: "इंटरनेट/नेटवर्कची समस्या", en: "connectivity issue" },
  cat_other: { hi: "अन्य समस्या", mr: "इतर समस्या", en: "other issue" },
  urg_high: { hi: "ज़रूरी", mr: "तातडीची", en: "high urgency" },
  urg_medium: { hi: "सामान्य", mr: "सामान्य", en: "medium urgency" },
  urg_low: { hi: "कम ज़रूरी", mr: "कमी तातडीची", en: "low urgency" },

  timeline_title: { hi: "आपकी शिकायत कहाँ तक पहुँची", mr: "तुमची तक्रार कुठपर्यंत पोहोचली", en: "Where your report is" },
  st_received: { hi: "आपकी बात मिल गई", mr: "तुमची तक्रार मिळाली", en: "Received" },
  st_understood: { hi: "हमने आपकी समस्या समझी", mr: "आम्ही तुमची समस्या समजून घेतली", en: "Understood" },
  st_grouped: { hi: "आस-पास की शिकायतों के साथ जोड़ा गया", mr: "जवळपासच्या तक्रारींसोबत जोडली", en: "Grouped with nearby reports" },
  st_under_review: { hi: "अधिकारी समीक्षा कर रहे हैं", mr: "अधिकारी आढावा घेत आहेत", en: "Under review by officials" },
  st_published: { hi: "सिफ़ारिश प्रकाशित हुई", mr: "शिफारस प्रसिद्ध झाली", en: "Recommendation published" },
  st_resolved: { hi: "समस्या हल होने की सूचना", mr: "समस्या सुटल्याची नोंद", en: "Reported resolved" },
  grouped_with: { hi: "{n} और लोगों की शिकायतों के साथ", mr: "आणखी {n} लोकांच्या तक्रारींसोबत", en: "with {n} others" },
  changes_requested: { hi: "अधिकारियों ने बदलाव माँगे", mr: "अधिकाऱ्यांनी बदल सुचवले", en: "changes requested" },
  not_approved: { hi: "इस बार स्वीकृत नहीं हुई", mr: "या वेळी मंजूर झाली नाही", en: "not approved this time" },
  retrying: { hi: "थोड़ी देर में दोबारा कोशिश होगी", mr: "थोड्या वेळाने पुन्हा प्रयत्न होईल", en: "will be retried shortly" },
  waiting_place: { hi: "जगह का नाम बताइए", mr: "ठिकाणाचे नाव सांगा", en: "waiting for the place name" },
  resolved_unverified: { hi: "पुष्टि बाक़ी — आपकी राय माँगी जाएगी", mr: "पडताळणी बाकी — तुमचे मत विचारले जाईल", en: "awaiting verification — we will ask you" },
  resolved_verified: { hi: "पुष्टि हो गई", mr: "पडताळणी झाली", en: "verified" },

  location_q: {
    hi: "हमें आपकी जगह पक्की नहीं मिली। कृपया गाँव, वार्ड या पास की किसी जगह का नाम लिखिए।",
    mr: "आम्हाला तुमचे ठिकाण नक्की सापडले नाही. कृपया गाव, वॉर्ड किंवा जवळच्या ठिकाणाचे नाव लिहा.",
    en: "We could not pin down your location. Please type your village, ward or a nearby landmark." },
  location_placeholder: { hi: "जैसे: वेल्हे", mr: "उदा. वेल्हे", en: "e.g. Velhe" },
  location_found: {
    hi: "धन्यवाद! जगह मिल गई — आपकी शिकायत आस-पास की शिकायतों के साथ जोड़ी गई।",
    mr: "धन्यवाद! ठिकाण सापडले — तुमची तक्रार जवळच्या तक्रारींसोबत जोडली.",
    en: "Thank you! Location found — your report is grouped with nearby reports." },
  location_unfound: {
    hi: "धन्यवाद। जगह अभी भी पक्की नहीं हुई, पर आपकी शिकायत सुरक्षित दर्ज है और अधिकारी इसे देखेंगे।",
    mr: "धन्यवाद. ठिकाण अजून नक्की झाले नाही, पण तुमची तक्रार सुरक्षित नोंदवली आहे आणि अधिकारी ती पाहतील.",
    en: "Thank you. We still could not place it, but your report is safely recorded and officials will see it." },

  verify_title: { hi: "आपके इलाक़े की समस्या हल बताई गई है", mr: "तुमच्या भागातील समस्या सुटल्याचे सांगितले आहे", en: "Officials report your area's issue as resolved" },
  verify_line: {
    hi: "क्या यह सच में ठीक हो गई? कृपया अभी की फोटो भेजिए, या माइक दबाकर बताइए।",
    mr: "ती खरोखर सुटली का? कृपया आताचा फोटो पाठवा, किंवा माइक दाबून सांगा.",
    en: "Is it really fixed? Please send a current photo, or press and hold the mic to tell us." },
  verify_issue: { hi: "समस्या: {summary}", mr: "समस्या: {summary}", en: "Issue: {summary}" },
  verify_photo: { hi: "📷 फोटो भेजिए", mr: "📷 फोटो पाठवा", en: "📷 Send photo" },
  verify_voice: { hi: "🎙️ दबाकर बोलिए", mr: "🎙️ दाबून बोला", en: "🎙️ Hold to speak" },
  verify_thanks: {
    hi: "धन्यवाद! आपका जवाब दर्ज हो गया है — इसकी जाँच की जाएगी।",
    mr: "धन्यवाद! तुमचे उत्तर नोंदवले आहे — त्याची तपासणी केली जाईल.",
    en: "Thank you! Your follow-up is recorded and will be checked." },
  photos: { hi: "📷 {n} फोटो", mr: "📷 {n} फोटो", en: "📷 {n} photos" },
  photo: { hi: "📷 फोटो", mr: "📷 फोटो", en: "📷 photo" },

  // Assisted field-worker mode (enhancements task 6.5).
  assisted_badge: { hi: "सहायक मोड", mr: "सहाय्यक मोड", en: "Assisted mode" },
  assisted_welcome: {
    hi: "सहायक मोड: आप गाँव वालों की ओर से शिकायत दर्ज कर रहे हैं। किसी का नाम या फ़ोन नंबर न लिखें। नेटवर्क न हो तो शिकायत फ़ोन में रखी जाएगी और नेटवर्क आने पर अपने-आप भेजी जाएगी।",
    mr: "सहाय्यक मोड: तुम्ही गावकऱ्यांच्या वतीने तक्रार नोंदवत आहात. कोणाचेही नाव किंवा फोन नंबर लिहू नका. नेटवर्क नसल्यास तक्रार फोनमध्ये ठेवली जाईल आणि नेटवर्क आल्यावर आपोआप पाठवली जाईल.",
    en: "Assisted mode: you are reporting on behalf of residents. Do not enter anyone's name or phone number. Without network, reports are kept on this phone and sent automatically when you are back online." },
  assisted_village: { hi: "गाँव / वार्ड", mr: "गाव / वॉर्ड", en: "Village / ward" },
  assisted_households: { hi: "कितने परिवार", mr: "किती कुटुंबे", en: "Households" },
  assisted_need_village: { hi: "कृपया गाँव या वार्ड का नाम लिखिए।", mr: "कृपया गाव किंवा वॉर्डचे नाव लिहा.", en: "Please enter the village or ward." },
  queue_count: { hi: "{n} शिकायतें भेजनी बाक़ी", mr: "{n} तक्रारी पाठवायच्या बाकी", en: "{n} waiting to send" },
  queue_empty: { hi: "सब भेज दी गईं", mr: "सर्व पाठवल्या", en: "All sent" },
  queued_offline: {
    hi: "नेटवर्क नहीं है — शिकायत फ़ोन में रखी गई, नेटवर्क आते ही भेजी जाएगी।",
    mr: "नेटवर्क नाही — तक्रार फोनमध्ये ठेवली, नेटवर्क आल्यावर पाठवली जाईल.",
    en: "No network — report kept on this phone and will be sent when you are back online." },
  queue_flushed: { hi: "{n} रखी हुई शिकायतें भेज दी गईं ✓", mr: "{n} ठेवलेल्या तक्रारी पाठवल्या ✓", en: "{n} saved reports sent ✓" },
};

let currentLang = "hi";
try {
  const saved = localStorage.getItem("setu_ui_lang");
  if (saved && LANGS[saved]) currentLang = saved;
} catch (_) { /* storage unavailable — default Hindi */ }

/** Fill {name} placeholders. A var given as {key: "..."} is itself a string
 *  key, translated into the SAME language as the line it fills — so the
 *  English subtitle never carries a Hindi category name. */
function fill(text, vars, lang) {
  return text.replace(/\{(\w+)\}/g, (_, k) => {
    if (!vars || !(k in vars)) return "";
    const v = vars[k];
    if (v && typeof v === "object" && v.key) {
      const e = STRINGS[v.key];
      return e ? (e[lang] || e.en) : v.key;
    }
    return String(v);
  });
}

/** {main, sub}: the chosen language, plus an English subtitle unless the
 *  chosen language is English. Unknown keys fall back to the key itself. */
function tr(key, vars) {
  const entry = STRINGS[key];
  if (!entry) return { main: key, sub: null };
  const main = fill(entry[currentLang] || entry.en, vars, currentLang);
  const sub = currentLang === "en" ? null : fill(entry.en, vars, "en");
  return { main, sub };
}

/** Plain string in the chosen language only (labels, placeholders). */
function t(key, vars) {
  return tr(key, vars).main;
}
