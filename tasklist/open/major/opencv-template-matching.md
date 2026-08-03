Title: Add OpenCV template/color matching as a new screen-detection mode alongside OCR
Prio:  11

Goal:  Screens and steps can be detected by OpenCV template or color matching, as an alternative to
       the existing OCR-text detection, for cases text recognition handles poorly (icons, color
       states, non-text UI elements).
Open:  Needs its own request/response protocol (parallel to ocr/'s ocr_req.txt/ocr_resp.txt file
       protocol) and its own config-schema extension, since today every detection field
       (DetectMapProfileInRegion, IsTextDetectedInRegion, Option Availability Check, Advanced
       Outcomes, Disconnect Detection) assumes a text string. Where does the matching engine live -
       a new ocr/-sibling process, or folded into ocr/ itself since it already owns image capture via
       mss? How does the GUI capture/store a template image (new capture flow next to the existing
       coordinate capture) and how is it edited/replaced later? Which of the existing detection
       fields gain this as an alternative mode vs. only new fields?
