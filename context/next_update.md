1. Official Government API (ABDM HPR) — recommended

Government provides Healthcare Professional Registry (HPR) APIs:

Register
Search doctors
Fetch details
Verify mobile / identity
Get HPR ID

These APIs are listed in official documentation.

This registry is a verified national database of healthcare professionals maintained under Ayushman Bharat Digital Mission.

How to get access
Go to
https://hpr.abdm.gov.in/apidocuments
Register as:
Healthcare app
Telemedicine platform
Hospital system
Get:
client_id
client_secret
sandbox access
Call search API:
GET /search?name=doctor
GET /fetch?registrationNo=xxxx
