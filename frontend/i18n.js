/* UI chrome translations. The assistant's spoken prompts come from the backend (app/i18n.py). */
window.LANGS = [
  { code: 'en', name: 'English', speech: 'en-IN' },
  { code: 'kn', name: 'ಕನ್ನಡ', speech: 'kn-IN' },
  { code: 'hi', name: 'हिन्दी', speech: 'hi-IN' },
  { code: 'ta', name: 'தமிழ்', speech: 'ta-IN' },
  { code: 'te', name: 'తెలుగు', speech: 'te-IN' },
];

window.UI = {
  nav_assistant: { en: 'Assistant', hi: 'सहायक', kn: 'ಸಹಾಯಕ', ta: 'உதவியாளர்', te: 'సహాయకుడు' },
  nav_requests: { en: 'Requests', hi: 'अनुरोध', kn: 'ವಿನಂತಿಗಳು', ta: 'கோரிக்கைகள்', te: 'అభ్యర్థనలు' },
  nav_donor: { en: 'Donor', hi: 'डोनर', kn: 'ದಾನಿ', ta: 'தானம்', te: 'దాత' },
  nav_banks: { en: 'Blood banks', hi: 'ब्लड बैंक', kn: 'ಬ್ಲಡ್ ಬ್ಯಾಂಕ್', ta: 'இரத்த வங்கி', te: 'బ్లడ్ బ్యాంక్' },
  nav_admin: { en: 'Admin', hi: 'एडमिन', kn: 'ಆಡಳಿತ', ta: 'நிர்வாகம்', te: 'అడ్మిన్' },
  tap_to_speak: { en: 'Tap and speak', hi: 'दबाइए और बोलिए', kn: 'ಒತ್ತಿ ಮಾತನಾಡಿ', ta: 'அழுத்திப் பேசுங்கள்', te: 'నొక్కి మాట్లాడండి' },
  listening: { en: 'Listening…', hi: 'सुन रहा हूँ…', kn: 'ಕೇಳುತ್ತಿದ್ದೇನೆ…', ta: 'கேட்கிறேன்…', te: 'వింటున్నాను…' },
  type_here: { en: 'Or type here…', hi: 'या यहाँ लिखें…', kn: 'ಅಥವಾ ಇಲ್ಲಿ ಟೈಪ್ ಮಾಡಿ…', ta: 'அல்லது இங்கே தட்டச்சு செய்க…', te: 'లేదా ఇక్కడ టైప్ చేయండి…' },
  send: { en: 'Send', hi: 'भेजें', kn: 'ಕಳುಹಿಸಿ', ta: 'அனுப்பு', te: 'పంపు' },
  understood: { en: 'What I understood', hi: 'मैंने क्या समझा', kn: 'ನಾನು ಅರ್ಥಮಾಡಿಕೊಂಡದ್ದು', ta: 'நான் புரிந்துகொண்டது', te: 'నేను అర్థం చేసుకున్నది' },
  blood_group: { en: 'Blood group', hi: 'ब्लड ग्रुप', kn: 'ಬ್ಲಡ್ ಗ್ರೂಪ್', ta: 'இரத்த வகை', te: 'బ్లడ్ గ్రూప్' },
  units: { en: 'Units', hi: 'यूनिट', kn: 'ಯೂನಿಟ್', ta: 'யூனிட்', te: 'యూనిట్లు' },
  hospital: { en: 'Hospital', hi: 'अस्पताल', kn: 'ಆಸ್ಪತ್ರೆ', ta: 'மருத்துவமனை', te: 'ఆసుపత్రి' },
  urgency: { en: 'Urgency', hi: 'तात्कालिकता', kn: 'ತುರ್ತು', ta: 'அவசரம்', te: 'అత్యవసరత' },
  name: { en: 'Name', hi: 'नाम', kn: 'ಹೆಸರು', ta: 'பெயர்', te: 'పేరు' },
  gender: { en: 'Gender', hi: 'लिंग', kn: 'ಲಿಂಗ', ta: 'பாலினம்', te: 'లింగం' },
  last_donation: { en: 'Last donation', hi: 'आखिरी दान', kn: 'ಕೊನೆಯ ದಾನ', ta: 'கடைசி தானம்', te: 'చివరి దానం' },
  area: { en: 'Area', hi: 'इलाका', kn: 'ಏರಿಯಾ', ta: 'பகுதி', te: 'ప్రాంతం' },
  accept: { en: 'Yes, I will come', hi: 'हाँ, मैं आऊँगा', kn: 'ಹೌದು, ಬರುತ್ತೇನೆ', ta: 'ஆம், வருகிறேன்', te: 'అవును, వస్తాను' },
  decline: { en: 'Not now', hi: 'अभी नहीं', kn: 'ಈಗ ಆಗಲ್ಲ', ta: 'இப்போது இல்லை', te: 'ఇప్పుడు కాదు' },
  checkin: { en: "I've reached the blood centre", hi: 'मैं ब्लड सेंटर पहुँच गया', kn: 'ನಾನು ಬ್ಲಡ್ ಸೆಂಟರ್ ತಲುಪಿದೆ', ta: 'நான் இரத்த மையத்தை அடைந்தேன்', te: 'నేను బ్లడ్ సెంటర్ చేరుకున్నాను' },
  available: { en: 'Available now', hi: 'अभी उपलब्ध', kn: 'ಈಗ ಲಭ್ಯ', ta: 'இப்போது கிடைக்கிறேன்', te: 'ఇప్పుడు అందుబాటులో' },
  busy: { en: 'Busy', hi: 'व्यस्त', kn: 'ಬ್ಯುಸಿ', ta: 'பிஸி', te: 'బిజీ' },
  unavailable: { en: 'Unavailable', hi: 'उपलब्ध नहीं', kn: 'ಲಭ್ಯವಿಲ್ಲ', ta: 'கிடைக்கவில்லை', te: 'అందుబాటులో లేదు' },
  emergency_near: { en: 'Emergency blood request near you', hi: 'आपके पास आपातकालीन रक्त अनुरोध', kn: 'ನಿಮ್ಮ ಹತ್ತಿರ ತುರ್ತು ರಕ್ತ ವಿನಂತಿ', ta: 'உங்கள் அருகில் அவசர இரத்த கோரிக்கை', te: 'మీ దగ్గర అత్యవసర రక్త అభ్యర్థన' },
  donor_accepted_say: { en: 'Good news. A donor has accepted and is on the way.', hi: 'अच्छी खबर। एक डोनर ने स्वीकार किया है और रास्ते में है।', kn: 'ಒಳ್ಳೆಯ ಸುದ್ದಿ. ಒಬ್ಬ ದಾನಿ ಒಪ್ಪಿದ್ದಾರೆ ಮತ್ತು ಬರುತ್ತಿದ್ದಾರೆ.', ta: 'நல்ல செய்தி. ஒரு தானம் செய்பவர் ஏற்றுக்கொண்டு வருகிறார்.', te: 'శుభవార్త. ఒక దాత అంగీకరించారు, వస్తున్నారు.' },
  checked_in_say: { en: 'The donor has reached the blood centre.', hi: 'डोनर ब्लड सेंटर पहुँच गया है।', kn: 'ದಾನಿ ಬ್ಲಡ್ ಸೆಂಟರ್ ತಲುಪಿದ್ದಾರೆ.', ta: 'தானம் செய்பவர் இரத்த மையத்தை அடைந்தார்.', te: 'దాత బ్లడ్ సెంటర్ చేరుకున్నారు.' },
  fulfilled_say: { en: 'Your blood request is fulfilled. Wishing the patient a quick recovery.', hi: 'आपका रक्त अनुरोध पूरा हुआ। मरीज़ के जल्द ठीक होने की कामना।', kn: 'ನಿಮ್ಮ ರಕ್ತ ವಿನಂತಿ ಪೂರ್ಣಗೊಂಡಿದೆ. ರೋಗಿ ಬೇಗ ಗುಣಮುಖರಾಗಲಿ.', ta: 'உங்கள் இரத்த கோரிக்கை நிறைவேறியது. நோயாளி விரைவில் குணமடைய வாழ்த்துகள்.', te: 'మీ రక్త అభ్యర్థన పూర్తయింది. రోగి త్వరగా కోలుకోవాలని కోరుకుంటున్నాం.' },
  escalated_say: { en: 'No response yet. I am alerting more donors.', hi: 'अभी तक जवाब नहीं आया। मैं और डोनर्स को सूचना भेज रहा हूँ।', kn: 'ಇನ್ನೂ ಉತ್ತರ ಬಂದಿಲ್ಲ. ಇನ್ನಷ್ಟು ದಾನಿಗಳಿಗೆ ಎಚ್ಚರಿಕೆ ಕಳುಹಿಸುತ್ತಿದ್ದೇನೆ.', ta: 'இன்னும் பதில் இல்லை. மேலும் தானம் செய்பவர்களுக்கு எச்சரிக்கை அனுப்புகிறேன்.', te: 'ఇంకా స్పందన లేదు. మరిన్ని దాతలకు హెచ్చరిక పంపుతున్నాను.' },
  login: { en: 'Log in', hi: 'लॉग इन', kn: 'ಲಾಗಿನ್', ta: 'உள்நுழை', te: 'లాగిన్' },
  logout: { en: 'Log out', hi: 'लॉग आउट', kn: 'ಲಾಗ್ ಔಟ್', ta: 'வெளியேறு', te: 'లాగ్ అవుట్' },
  voice_on: { en: 'Voice replies on', hi: 'आवाज़ चालू', kn: 'ಧ್ವನಿ ಆನ್', ta: 'குரல் இயக்கம்', te: 'వాయిస్ ఆన్' },
  voice_off: { en: 'Voice replies off', hi: 'आवाज़ बंद', kn: 'ಧ್ವನಿ ಆಫ್', ta: 'குரல் நிறுத்தம்', te: 'వాయిస్ ఆఫ్' },
  start_over: { en: 'Start over', hi: 'फिर से शुरू', kn: 'ಮತ್ತೆ ಶುರು', ta: 'மீண்டும் தொடங்கு', te: 'మళ్ళీ ప్రారంభించు' },
};

window.tr = function (key, lang) {
  const row = window.UI[key];
  if (!row) return key;
  return row[lang] || row.en;
};
