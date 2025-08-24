from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from pdf2image import convert_from_bytes
from PIL import Image
import base64, re, json
from io import BytesIO
import openai
import os
import json
from dotenv import load_dotenv
load_dotenv(".env")
import requests
from pymongo import MongoClient
MONGO_URI = os.getenv("mongourl")
client = MongoClient(MONGO_URI)
db = client["ocrdb"]
openai.api_key = os.getenv("openaikey")
SENDER_API = "https://ocr-bck.onrender.com/api/sender"
app = FastAPI(title="Company Info Extractor")
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Company Info Extractor")

# CORS settings
origins = [
    "http://localhost:5173",  # Vite dev server
    "http://127.0.0.1:5173",
    "https://your-vercel-app.vercel.app",
    "https://your-netlify-app.netlify.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # allow only these URLs
    allow_credentials=True,
    allow_methods=["*"],    # allow GET, POST, etc.
    allow_headers=["*"],    # allow all headers
)

def pil_to_base64(img: Image.Image):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def extract_company_info_from_image(img: Image.Image):
    img_b64 = pil_to_base64(img)
    prompt = """
    You are an information extraction system. Extract company information from this document screenshot. 
    Return result strictly in JSON with keys: both sender and receiver company name should be there those text you find from to columns or similar columns 
    and how much the vender is quoting the excluding tax price+tax price and its percentage and hsn code
    can you verify the gsn code and tax rate is correct as an additional key if false why correct hsn code 
    - company_name - 
    tax_id - 
    address - 
    email - 
    phone - 
    website -
    just give the output in the form plain output json
    sample output
    {
    "sender": {
        "company_name": "LEXODD Hypernova Pvt. Ltd.",
        "tax_id": "37AAFCL3652F1ZJ",
        "address": "8-44-26/1, OLD Cbi Down, 530003 & Visakhapatnam",
        "email": "lexoddgroup@gmail.com", #if empty can be null
        "phone": +91 6281110153", #if empty can be null
        "website": "www.sample.com" #if empty can be null
    },
    "receiver": {
        "company_name": "Orogen Naturals",
        "tax_id": "36AARFN9347A1ZZ",
        "address": "7-1-619 /A /24,24/1,24/2 /201, Gayatri Nagar Hyderabad, Telangana 500038",
        "email": "lexoddgroup@gmail.com", #if empty can be null
        "phone": +91 6281110153", #if empty can be null
        "website": "www.sample.com"  #if empty can be null
    },
    "quotation": {
        "excluding_tax_price": "₹20,000",
        "tax_price": "₹3,600",
        "tax_percentage": "18%",
        "hsn_code": "998314"
    },
    "verification": {
        "hsn_code_correct": true,
        "tax_rate_correct": true
    }
}
similary for false
{
    "sender": {
        "company_name": "LEXODD Hypernova Pvt. Ltd.",
        "tax_id": "37AAFCL3652F1ZJ",
        "address": "8-44-26/1, OLD Cbi Down, 530003 & Visakhapatnam",
        "email": "lexoddgroup@gmail.com", #if empty can be null
        "phone": +91 6281110153", #if empty can be null
        "website": "www.sample.com" #if empty can be null
    },
    "receiver": {
        "company_name": "Orogen Naturals",
        "tax_id": "36AARFN9347A1ZZ",
        "address": "7-1-619 /A /24,24/1,24/2 /201, Gayatri Nagar Hyderabad, Telangana 500038",
        "email": "lexoddgroup@gmail.com", #if empty can be null
        "phone": +91 6281110153", #if empty can be null
        "website": "www.sample.com" #if empty can be null
        }
    "quotation": {
        "excluding_tax_price": "₹20,000",
        "tax_price": "₹3,600",
        "tax_percentage": "18%",
        "hsn_code": "998314"
    },
    "verification": {
        "hsn_code_correct": false,
        "tax_rate_correct": false,
        "correct_hsn_code":corrected value,
        "correct_tax_code":corrected tax code,
    }
}
### do not confuse mail id with website and write '''json ''' in the output json file
    """
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                ]
            }
        ],
        temperature=0
    )

    try:
        return json.loads(response.choices[0].message.content)
    except:
        return {"raw_response": response.choices[0].message.content}


def process_pdf(pdf_bytes: bytes):
    pages = convert_from_bytes(pdf_bytes, dpi=200)
    results = []
    for page in pages:
        results.append(extract_company_info_from_image(page))
    final_info = {}
    for res in results:
        if isinstance(res, dict):
            for k, v in res.items():
                if v and (k not in final_info or not final_info[k]):
                    final_info[k] = v
    return final_info



def process_image(image_bytes: bytes):
    img = Image.open(BytesIO(image_bytes))
    return extract_company_info_from_image(img)

def clean_and_print(response: dict):
    raw = response.get("raw_response", "")

    # 1️⃣ Remove ```json, ``` and extra spaces
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()

    # 2️⃣ Some models return fenced block with both start & end lines → strip all
    cleaned = re.sub(r"```(?:json)?", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
        pretty = json.dumps(parsed, indent=4, ensure_ascii=False)
        print(pretty)
        return parsed   # return dict
    except json.JSONDecodeError as e:
        print("⚠️ Failed to parse JSON")
        print("Reason:", e)
        print("Raw cleaned output:\n", cleaned)
        return raw
    

# --- FastAPI Routes ---
# @app.post("/extract")
# async def extract_company_info(file: UploadFile = File(...)):
#     try:
#         contents = await file.read()
#         if file.filename.lower().endswith(".pdf"):
#             result = process_pdf(contents)
#         else:
#             result = process_image(contents)

#         return JSONResponse(content=clean_and_print(result))
#     except Exception as e:
#         return JSONResponse(content={"error": str(e)}, status_code=500)
@app.get("/health")
def health():
    return {"status": "ok"}
from bson import ObjectId

def serialize_mongo_doc(doc):
    if not doc:
        return None
    doc = dict(doc)
    if "_id" in doc and isinstance(doc["_id"], ObjectId):
        doc["_id"] = str(doc["_id"])
    return doc


@app.post("/validate_invoice")
async def validate_invoice(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        if file.filename.lower().endswith(".pdf"):
            extracted = process_pdf(contents)
        else:
            extracted = process_image(contents)

        extracted = clean_and_print(extracted)
        if not isinstance(extracted, dict):
            return JSONResponse(content={"error": "Invalid extraction format"}, status_code=400)

        sender = extracted.get("sender")
        receiver = extracted.get("receiver")
        quotation = extracted.get("quotation", {})

        validation_result = {
            "sender_valid": False,
            "receiver_valid": False,
            "hsn_valid": False
        }

        # Validate Sender
        if sender and sender.get("company_name"):
            sender_match = db["senders"].find_one({
                "$or": [
                    {"company_name": sender["company_name"]},
                    {"registration_number": sender.get("tax_id")}
                ]
            })
            if sender_match:
                validation_result["sender_valid"] = True
                validation_result["sender_db_record"] = serialize_mongo_doc(sender_match)

        # Validate Receiver
        if receiver and receiver.get("company_name"):
            receiver_match = db["receivers"].find_one({
                "$or": [
                    {"company_name": receiver["company_name"]},
                    {"registration_number": receiver.get("tax_id")}
                ]
            })
            if receiver_match:
                validation_result["receiver_valid"] = True
                validation_result["receiver_db_record"] = serialize_mongo_doc(receiver_match)

        #Validate HSN
        if quotation and quotation.get("hsn_code"):
            hsn_match = db["hsns"].find_one({"hsn_code": quotation["hsn_code"]})
            if hsn_match:
                validation_result["hsn_valid"] = True
                validation_result["hsn_db_record"] = serialize_mongo_doc(hsn_match)

                # check tax %
                if quotation.get("tax_percentage"):
                    db_tax = str(hsn_match.get("tax_percentage")).replace("%", "")
                    q_tax = str(quotation["tax_percentage"]).replace("%", "")
                    if db_tax != q_tax:
                        validation_result["hsn_valid"] = False
                        validation_result["correct_tax_percentage"] = hsn_match["tax_percentage"]

        overall_status = "validated , results are correct" if all([
            validation_result["sender_valid"],
            validation_result["receiver_valid"],
            validation_result["hsn_valid"]
        ]) else "mismatches are there"

        results = {
            "status": overall_status,
            "extracted": extracted,
            "validation": validation_result
        }
        return JSONResponse(content=results)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/")
def root():
    return {"message": "Company Info Extraction API is running 🚀"}
