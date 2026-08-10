Title: Give [General] OcrMatchThreshold a field in the GUI
Prio:  5

Goal:  The OCR match threshold introduced with the scoring rule is editable in the General tab
       instead of only by hand-editing config.ini, so a user whose detections score just under the
       default can fix that without a text editor.
Open:  Which widget and where in the General tab, next to the Disconnect Detection block or in its
       own row? The value is a 0.30 to 1.00 fraction, so a QDoubleSpinBox with 2 decimals and a
       0.05 step is the obvious choice, but the log reports scores as "0.61 < 0.75" and a percent
       spin box (61% / 75%) may read better to a non-technical user; pick one and use the same
       formatting in the log. Should the field also surface the last detection's score somewhere,
       or is the log enough?
