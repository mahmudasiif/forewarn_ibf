"""Deterministic fallback narrative — ported verbatim from the fallbackNarrative()
in src/app/api/guideline/route.ts. Used when the LLM is unavailable or fails, so
a guideline is always produced. The first populationAndHouse bullet is the
structural housing-damage fact, injected via the passed helper.
"""
from __future__ import annotations

from collections.abc import Callable


def fallback_narrative(ctx: dict, lang: str, housing_damage_fact: Callable[[dict, str], str]) -> dict:
    if lang == "en":
        return {
            "majorImpact": {
                "populationAndHouse": [
                    housing_damage_fact(ctx, lang),
                    "Households in weak or low-lying houses may have to leave for the nearest cyclone shelter, and children, older people and persons with disabilities may need help to move.",
                    "Women, children, older people, persons with disabilities and single-parent households may face the greatest shelter and transport difficulty; verify their needs in the field.",
                ],
                "infrastructurePolder": [
                    "Strong wind may break weak roofs, signboards, trees and poles and block village and emergency roads.",
                    "Depending on surge and rainfall values, embankments, sluice gates and drainage channels may breach, overtop or block.",
                ],
                "agriculture": [
                    "Wind may lodge or break standing crops and shed leaves and fruit, and rainfall may waterlog fields and damage roots.",
                    "A saline surge may salinise cropland and seedbeds, and harvested crops, seed and fertiliser stored at ground level may be spoiled.",
                ],
                "livestockFisheries": [
                    "Livestock and poultry left in low-lying sheds are at risk; they may need moving in advance to raised ground, a safe location or a killa, with fodder and safe drinking water stocked.",
                    "Low-lying farms and fish/shrimp enclosures may flood, stock may escape, and feed and medicine may be spoiled by water.",
                ],
                "livelihood": [
                    "If markets, transport and workplaces close, daily income and goods supply may be disrupted, hitting women-headed, landless and daily-income families hardest.",
                    "If ghats, waterways or roads close, movement of goods and workers may stop, and boats, gear, stalls and tools left outside may be damaged.",
                ],
                "healthDisease": [
                    "Flood water raises the risk of diarrhoea and skin disease, and crowded shelters raise the risk of respiratory infection.",
                    "Broken tin, glass, trees and live wires create injury and electrocution risk, particularly for children.",
                ],
                "utilityService": [
                    "Falling trees and branches may damage electricity poles and lines, cutting power for a prolonged period.",
                    "If power fails, backup batteries and generators at mobile BTS/towers may run out and weaken the network.",
                    "Saline and flood water may contaminate tube wells and stored water.",
                    "Trees, standing water and broken culverts may block roads, including routes to hospitals and shelters.",
                ],
            },
            "advisories": {
                "community": {
                    "populationAndHouse": [
                        "Complete evacuation from coastal, riverbank and low-lying areas based on the official signal, local surge height and route safety.",
                        "Carry dry food, safe water, medicine and documents to the shelter, and help neighbours who cannot move on their own.",
                        "Secure the roofing, posts and joints of kancha and semi-pucca houses with rope or GI wire.",
                        "Seal important papers and documents in a waterproof or polythene bag and carry them with you to the shelter — do not bury them in the ground or leave them at home.",
                    ],
                    "infrastructurePolder": [
                        "Report any breach, overtopping or blockage of embankments, sluice gates or drains to the local administration immediately.",
                        "Keep clear of fallen power lines, damaged poles and unstable structures on roads and paths.",
                    ],
                    "agriculture": [
                        "Harvest mature crops early where possible and protect seedbeds and stored seed from waterlogging and saline water.",
                    ],
                    "livestockFisheries": [
                        "Move livestock and poultry in advance to raised ground, a safe location or a killa, and stock fodder and safe drinking water.",
                        "Secure or harvest fish and shrimp enclosures where flooding is likely, and move feed and medicine to higher, dry storage.",
                    ],
                    "livelihood": [
                        "Move boats, nets, tools and shop stock to a safe place and note what had to be left behind.",
                    ],
                    "healthDisease": [
                        "Anyone who is unwell — fever, cough or cold, breathing difficulty or any infectious illness — should wear a mask inside the shelter to reduce transmission in crowded conditions.",
                    ],
                    "utilityService": [
                        "Keep a torch, spare batteries, a power bank and a charged phone ready, and store safe water before the power goes out.",
                    ],
                },
                "institutional": {
                    "populationAndHouse": [
                        "Open shelters before landfall and ensure lighting, safe water, sanitation, women/child protection and disability-friendly access.",
                        "Verify house location, build quality, roof connections and cyclone-resistant features in the field and act by house type; do not apply one damage level to all houses.",
                        "Record house type, damage level, photos/coordinates and verification time separately in the damage report.",
                    ],
                    "infrastructurePolder": [
                        "Identify emergency roads, ambulance routes, ghats and communication alternatives, and assign responsible teams.",
                        "Inspect embankments, sluice gates and drainage before landfall, and prioritise repair of roads, bridges and culverts afterward.",
                    ],
                    "agriculture": [
                        "Record crop name, sowing/flowering/fruiting/harvest stage and depth of waterlogging in the field.",
                        "Separate losses caused by saline intrusion, wind lodging and destroyed seedbeds.",
                    ],
                    "livestockFisheries": [
                        "Keep livestock transport vehicles and an emergency veterinary team ready, and confirm that killa and shelter access routes are usable.",
                    ],
                    "livelihood": [
                        "Collect, by occupation, the number of days work stops, market/route closures and the scale of income loss.",
                        "In support planning, account for the recovery time of women-headed, landless and daily-income households.",
                    ],
                    "healthDisease": [
                        "Monitor diarrhoea, skin disease, respiratory problems, injury and electrocution separately, and maintain safe water, sanitation and infection control at shelters.",
                    ],
                    "utilityService": [
                        "Ask electricity and mobile operators to keep emergency restoration teams, poles/wires, generators, batteries and fuel ready.",
                        "Log outages separately for electricity feeders/poles/lines, mobile BTS and backhaul, water sources and emergency roads; give hospitals, shelters, water supply and administrative communication first restoration priority.",
                    ],
                },
            },
        }
    return {
        "majorImpact": {
            "populationAndHouse": [
                housing_damage_fact(ctx, lang),
                "দুর্বল বা নিচু এলাকার ঘরের পরিবারগুলোকে নিকটবর্তী আশ্রয়কেন্দ্রে যেতে হতে পারে; শিশু, প্রবীণ ও প্রতিবন্ধী সদস্যদের সরাতে সহায়তা লাগতে পারে।",
                "নারী, শিশু, প্রবীণ, প্রতিবন্ধী ব্যক্তি ও একক-অভিভাবক পরিবার আশ্রয় ও যাতায়াতে সবচেয়ে বেশি সমস্যায় পড়তে পারেন; তাঁদের চাহিদা মাঠে যাচাই করুন।",
            ],
            "infrastructurePolder": [
                "ঝড়ো বাতাসে দুর্বল ছাদ, সাইনবোর্ড, গাছ ও খুঁটি ভেঙে গ্রামীণ ও জরুরি সড়ক অবরুদ্ধ হতে পারে।",
                "জলোচ্ছ্বাস ও বৃষ্টির মান অনুযায়ী বাঁধ, স্লুইসগেট ও নিষ্কাশন পথে ভাঙন, উপচে পড়া বা ব্লকেজ হতে পারে।",
            ],
            "agriculture": [
                "বাতাসে ফসল হেলে বা ভেঙে পড়া, পাতা-ফল ঝরা এবং বৃষ্টিতে জমি জলাবদ্ধ হয়ে শিকড়ের ক্ষতি হতে পারে।",
                "লবণাক্ত জলোচ্ছ্বাসে ফসলি জমি ও বীজতলা লবণাক্ত হতে পারে এবং নিচু স্থানে রাখা কাটা ফসল, বীজ ও সার নষ্ট হতে পারে।",
            ],
            "livestockFisheries": [
                "নিচু গোয়ালঘরে থাকা গবাদিপশু ও হাঁস-মুরগি ঝুঁকিতে পড়তে পারে; আগেভাগে উঁচু নিরাপদ স্থানে বা কিল্লায় সরানো এবং পশুখাদ্য ও নিরাপদ পানির মজুত প্রয়োজন হতে পারে।",
                "নিচু খামার ও মাছের ঘেরে প্লাবন, মাছ বেরিয়ে যাওয়া এবং খাদ্য ও ওষুধ ভিজে নষ্ট হওয়ার ঝুঁকি রয়েছে।",
            ],
            "livelihood": [
                "বাজার, পরিবহন ও কর্মস্থল বন্ধ থাকলে দৈনিক আয় ও পণ্য সরবরাহ ব্যাহত হতে পারে; নারী-নেতৃত্বাধীন, ভূমিহীন ও দৈনিক আয়নির্ভর পরিবার সবচেয়ে বেশি ক্ষতিগ্রস্ত হতে পারে।",
                "ঘাট, নৌপথ বা সড়ক বন্ধ হলে পণ্য ও শ্রমিক চলাচল থামতে পারে এবং বাইরে রাখা নৌকা, জাল, দোকান ও সরঞ্জাম ক্ষতিগ্রস্ত হতে পারে।",
            ],
            "healthDisease": [
                "প্লাবিত পানিতে ডায়রিয়া ও চর্মরোগের ঝুঁকি বাড়ে এবং ভিড়পূর্ণ আশ্রয়কেন্দ্রে শ্বাসতন্ত্রের সংক্রমণের ঝুঁকি থাকে।",
                "ভাঙা টিন, কাচ, গাছ ও বিদ্যুতের তারে আঘাত ও বিদ্যুৎস্পৃষ্ট হওয়ার ঝুঁকি থাকে, বিশেষ করে শিশুদের জন্য।",
            ],
            "utilityService": [
                "গাছ ও ডাল পড়ে বিদ্যুতের খুঁটি ও তার ক্ষতিগ্রস্ত হয়ে দীর্ঘ সময় বিদ্যুৎ বিচ্ছিন্ন থাকতে পারে।",
                "বিদ্যুৎ বিচ্ছিন্ন হলে মোবাইল BTS/টাওয়ারের ব্যাকআপ ব্যাটারি ও জেনারেটর শেষ হয়ে নেটওয়ার্ক দুর্বল হতে পারে।",
                "লবণাক্ত ও প্লাবিত পানি নলকূপ ও সংরক্ষিত পানি দূষিত করতে পারে।",
                "গাছ, জমে থাকা পানি ও ভাঙা কালভার্টে সড়ক বন্ধ হয়ে হাসপাতাল ও আশ্রয়কেন্দ্রের পথও আটকে যেতে পারে।",
            ],
        },
        "advisories": {
            "community": {
                "populationAndHouse": [
                    "উপকূল, নদীতীর ও নিচু এলাকা থেকে সরে যাওয়া সরকারি সংকেত, স্থানীয় জলোচ্ছ্বাস উচ্চতা ও পথের নিরাপত্তার ভিত্তিতে শেষ করুন।",
                    "শুকনো খাবার, নিরাপদ পানি, ওষুধ ও কাগজপত্র সঙ্গে নিয়ে আশ্রয়কেন্দ্রে যান এবং যাঁরা নিজে যেতে পারেন না তাঁদের সহায়তা করুন।",
                    "কাঁচা ও আধা-পাকা ঘরের ছাউনি, খুঁটি ও সংযোগ দড়ি বা জিআই তার দিয়ে শক্ত করে বাঁধুন।",
                    "গুরুত্বপূর্ণ কাগজপত্র ও দলিল ওয়াটারপ্রুফ বা পলিথিন ব্যাগে ভরে সঙ্গে করে আশ্রয়কেন্দ্রে নিয়ে যান — মাটির নিচে পুঁতে রাখবেন না বা ঘরে ফেলে যাবেন না।",
                ],
                "infrastructurePolder": [
                    "বাঁধ, স্লুইসগেট বা নিষ্কাশন পথে ভাঙন, উপচে পড়া বা ব্লকেজ দেখলে সঙ্গে সঙ্গে স্থানীয় প্রশাসনকে জানান।",
                    "সড়ক ও পথে পড়ে থাকা বিদ্যুতের তার, ভাঙা খুঁটি ও অস্থিতিশীল কাঠামো থেকে দূরে থাকুন।",
                ],
                "agriculture": [
                    "সম্ভব হলে পরিপক্ব ফসল আগেভাগে কেটে নিন এবং বীজতলা ও সংরক্ষিত বীজ জলাবদ্ধতা ও লবণাক্ত পানি থেকে রক্ষা করুন।",
                ],
                "livestockFisheries": [
                    "গবাদিপশু ও হাঁস-মুরগি আগেভাগে উঁচু নিরাপদ স্থানে বা কিল্লায় সরান এবং পশুখাদ্য ও নিরাপদ পানির মজুত রাখুন।",
                    "প্লাবনের ঝুঁকি থাকা মাছ ও চিংড়ির ঘের সুরক্ষিত করুন বা মাছ ধরে ফেলুন, এবং খাদ্য ও ওষুধ উঁচু শুকনো স্থানে সরান।",
                ],
                "livelihood": [
                    "নৌকা, জাল, সরঞ্জাম ও দোকানের মালামাল নিরাপদ স্থানে সরিয়ে রাখুন এবং যা ফেলে যেতে হলো তা লিখে রাখুন।",
                ],
                "healthDisease": [
                    "যাঁদের অসুস্থতা (জ্বর, সর্দি-কাশি, শ্বাসকষ্ট বা সংক্রামক রোগ) রয়েছে, তাঁরা আশ্রয়কেন্দ্রে অবশ্যই মাস্ক পরবেন — ভিড়ের মধ্যে রোগ ছড়ানোর ঝুঁকি কমাতে।",
                ],
                "utilityService": [
                    "টর্চ, অতিরিক্ত ব্যাটারি, পাওয়ার ব্যাংক ও চার্জ দেওয়া মোবাইল প্রস্তুত রাখুন এবং বিদ্যুৎ যাওয়ার আগেই নিরাপদ পানি সংরক্ষণ করুন।",
                ],
            },
            "institutional": {
                "populationAndHouse": [
                    "ল্যান্ডফলের আগে আশ্রয়কেন্দ্র খুলে আলো, নিরাপদ পানি, স্যানিটেশন, নারী/শিশু সুরক্ষা ও প্রতিবন্ধীবান্ধব প্রবেশ নিশ্চিত করুন।",
                    "ঘরের অবস্থান, নির্মাণমান, ছাদের সংযোগ ও cyclone-resistant বৈশিষ্ট্য মাঠে যাচাই করে ঘরভেদে আলাদা ব্যবস্থা নিন; একই ক্ষতির মাত্রা সব ঘরে প্রয়োগ করবেন না।",
                    "ক্ষয়ক্ষতি রিপোর্টে ঘরের ধরন, ক্ষতির মাত্রা, ছবি/স্থানাঙ্ক ও যাচাই সময় আলাদাভাবে নথিভুক্ত করুন।",
                ],
                "infrastructurePolder": [
                    "জরুরি সড়ক, অ্যাম্বুলেন্স রুট, ঘাট ও যোগাযোগ বিকল্প চিহ্নিত করে দায়িত্বপ্রাপ্ত দল নির্ধারণ করুন।",
                    "ল্যান্ডফলের আগে বাঁধ, স্লুইসগেট ও নিষ্কাশন পরিদর্শন করুন, এবং পরে সড়ক, সেতু ও কালভার্ট মেরামতে অগ্রাধিকার দিন।",
                ],
                "agriculture": [
                    "ফসলের নাম, রোপণ/ফুল/ফল/কাটার পর্যায় ও জমির জলাবদ্ধতার গভীরতা মাঠে নথিভুক্ত করুন।",
                    "লবণাক্ত পানি প্রবেশ, বাতাসে হেলে পড়া ও বীজতলা নষ্ট হওয়ার ক্ষতি আলাদা করুন।",
                ],
                "livestockFisheries": [
                    "পশু পরিবহনের যানবাহন ও জরুরি পশুচিকিৎসা দল প্রস্তুত রাখুন এবং কিল্লা ও আশ্রয়কেন্দ্রে যাওয়ার পথ চলাচল-উপযোগী কি না নিশ্চিত করুন।",
                ],
                "livelihood": [
                    "কাজ বন্ধ থাকার দিন, বাজার ও রুট বন্ধ এবং আয় হারানোর পরিমাণ পেশাভিত্তিকভাবে সংগ্রহ করুন।",
                    "সহায়তা পরিকল্পনায় নারী-নেতৃত্বাধীন, ভূমিহীন ও দৈনিক আয়নির্ভর পরিবারের পুনরুদ্ধার সময় বিবেচনা করুন।",
                ],
                "healthDisease": [
                    "ডায়রিয়া, চর্মরোগ, শ্বাসতন্ত্রের সমস্যা, আঘাত ও বিদ্যুৎস্পৃষ্ট হওয়ার নজরদারি আলাদা রাখুন এবং আশ্রয়কেন্দ্রে নিরাপদ পানি, স্যানিটেশন ও সংক্রমণ নিয়ন্ত্রণ নিশ্চিত করুন।",
                ],
                "utilityService": [
                    "বিদ্যুৎ ও মোবাইল অপারেটরকে জরুরি পুনরুদ্ধার দল, খুঁটি/তার, জেনারেটর, ব্যাটারি ও জ্বালানি প্রস্তুত রাখতে বলুন।",
                    "বিদ্যুৎ feeder/খুঁটি/তার, মোবাইল BTS ও backhaul, পানির উৎস এবং জরুরি সড়কের outage আলাদাভাবে লগ করুন; হাসপাতাল, আশ্রয়কেন্দ্র, পানি সরবরাহ ও প্রশাসনিক যোগাযোগকে পুনরুদ্ধারে প্রথম অগ্রাধিকার দিন।",
                ],
            },
        },
    }
