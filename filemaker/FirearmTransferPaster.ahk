; ============================================================
;  FirearmTransferPaster.ahk  —  AutoHotkey v2
;  Hotkey: Ctrl+Alt+V
;
;  1. Open the Firearm Transfer Log record in ERPNext and click
;     "Copy to Clipboard".
;  2. In FileMaker, click into the FIRST field of the entry
;     layout (the "Date Received" field — field #0 below).
;  3. Press Ctrl+Alt+V.
;
;  The script reads the labeled clipboard block written by the
;  "Copy to Clipboard" button (KEY: value per line) and tabs
;  through the FileMaker layout, typing into the fields that
;  apply to the transfer's direction (Received/Sent) and
;  skipping the ones that don't — mirroring the exact tab order
;  documented below.
;
;  FileMaker tab order (0-18), confirmed field-by-field against
;  the real layout:
;    0  Date Received                         [Received only]
;    1  Received-from paragraph (autocomplete) [Received only]
;    2  Sent-to paragraph (autocomplete)       [Sent only]
;    3  Sent-to street                         [Sent only]
;    4  Sent-to city                           [Sent only]
;    5  Sent-to zip                            [Sent only]
;    6  Sent-to FFL#                           [Sent only]
;    7  Date Sent                              [Sent only]
;    8  Serial # (pre-filled on Sent)          [Received only]
;    9  Manufacturer (always pre-filled)       [skip always]
;    10 Model (always pre-filled)               [skip always]
;    11 Type: RIFLE/PISTOL (autocomplete)      [Sent only]
;    12 Caliber (autocomplete)                 [Sent only]
;    13 Notes                                  [both]
;    14 Shipped? radio, Yes default            [Yes=Sent, No=Received]
;    15 (unlabeled)                            [skip always]
;    16 Sent-to state                          [Sent only]
;    17 (unlabeled)                            [skip always]
;    18 Modal: In Inventory / Sold To Dealer   [In Inventory=Received, Sold To Dealer=Sent]
;
;  Fields marked "autocomplete" pop up a suggestion when you tab
;  in; FileMaker requires a Backspace before typing to dismiss it.
; ============================================================

#Requires AutoHotkey v2.0
SendMode "Input"

; Set to false once you've verified the sequence against a scratch
; FileMaker record. While true, no keystrokes are sent — you get a
; summary popup of exactly what each field would receive instead.
DryRun := true

; Milliseconds to wait between each keystroke/action. Raise this if
; FileMaker is dropping or reordering keystrokes on a slower machine.
SleepMs := 100

^!v:: {
	global DryRun, SleepMs, DryLog

	data := ParseClipboard(A_Clipboard)
	direction := data.Get("DIRECTION", "")

	if (direction != "Received" && direction != "Sent") {
		MsgBox "Clipboard doesn't contain a valid DIRECTION (Received/Sent).`n`nUse the 'Copy to Clipboard' button on the Firearm Transfer Log first.", "FirearmTransferPaster", "Icon!"
		return
	}

	DryLog := ""

	if (direction = "Received")
		EnterReceived(data)
	else
		EnterSent(data)

	if (DryRun)
		MsgBox "DRY RUN — " direction "`n`nNo keys were sent. Review the sequence below, then set DryRun := false to run for real.`n`n" DryLog, "FirearmTransferPaster (dry run)"
}

; ---- Field sequence, direction by direction --------------------

EnterReceived(data) {
	; Cursor starts on field 0, Date Received.
	TypeField(data.Get("DATE", ""), false, "0. Date Received")
	TypeField(data.Get("RECEIVED_PARAGRAPH", ""), true, "1. Received-from paragraph")
	SkipField("2. Sent-to paragraph")
	SkipField("3. Sent-to street")
	SkipField("4. Sent-to city")
	SkipField("5. Sent-to zip")
	SkipField("6. Sent-to FFL#")
	SkipField("7. Date Sent")
	TypeField(data.Get("SERIAL", ""), false, "8. Serial number")
	SkipField("9. Manufacturer")
	SkipField("10. Model")
	SkipField("11. Type")
	SkipField("12. Caliber")
	TypeField(data.Get("NOTES", ""), false, "13. Notes")
	RadioSelect(1, "14. Shipped? -> No")
	SkipField("15. (unlabeled)")
	SkipField("16. Sent-to state")
	SkipField("17. (unlabeled)")
	ModalSelect(0, "18. Modal -> In Inventory (default)")
}

EnterSent(data) {
	; Cursor starts on field 0, Date Received.
	SkipField("0. Date Received")
	SkipField("1. Received-from paragraph")
	TypeField(data.Get("SENT_PARAGRAPH", ""), true, "2. Sent-to paragraph")
	TypeField(data.Get("STREET", ""), false, "3. Sent-to street")
	TypeField(data.Get("CITY", ""), false, "4. Sent-to city")
	TypeField(data.Get("ZIP", ""), false, "5. Sent-to zip")
	TypeField(data.Get("FFL", ""), false, "6. Sent-to FFL#")
	TypeField(data.Get("DATE", ""), false, "7. Date Sent")
	SkipField("8. Serial number")
	SkipField("9. Manufacturer")
	SkipField("10. Model")
	TypeField(data.Get("TYPE", ""), true, "11. Type")
	TypeField(data.Get("CALIBER", ""), true, "12. Caliber")
	TypeField(data.Get("NOTES", ""), false, "13. Notes")
	RadioSelect(0, "14. Shipped? -> Yes (default)")
	SkipField("15. (unlabeled)")
	TypeField(data.Get("STATE", ""), false, "16. Sent-to state")
	SkipField("17. (unlabeled)")
	ModalSelect(1, "18. Modal -> Sold To Dealer")
}

; ---- Low-level helpers ------------------------------------------

; Types text into the current field and tabs to the next one.
; needsBackspace dismisses FileMaker's autocomplete suggestion first.
; Embedded newlines (from the *_PARAGRAPH values) are sent as
; genuine Enter presses so multi-line "paragraph" fields line-wrap
; the way FileMaker expects.
TypeField(text, needsBackspace := false, label := "") {
	global DryRun, SleepMs, DryLog
	if (DryRun) {
		DryLog .= label ": TYPE `"" text "`"`n"
		return
	}

	if (needsBackspace) {
		SendInput "{Backspace}"
		Sleep SleepMs
	}

	lines := StrSplit(text, "`n")
	for index, line in lines {
		SendText line
		Sleep SleepMs
		if (index < lines.Length) {
			SendInput "{Enter}"
			Sleep SleepMs
		}
	}

	SendInput "{Tab}"
	Sleep SleepMs
}

; Tabs past a field without touching it.
SkipField(label := "") {
	global DryRun, SleepMs, DryLog
	if (DryRun) {
		DryLog .= label ": skip`n"
		return
	}
	SendInput "{Tab}"
	Sleep SleepMs
}

; Shipped? Yes/No radio. Yes is the default (highlighted, downCount=0);
; No is one Down below it (downCount=1).
RadioSelect(downCount, label := "") {
	global DryRun, SleepMs, DryLog
	if (DryRun) {
		DryLog .= label "`n"
		return
	}
	Loop downCount {
		SendInput "{Down}"
		Sleep SleepMs
	}
	SendInput "{Space}"
	Sleep SleepMs
	SendInput "{Tab}"
	Sleep SleepMs
}

; In Inventory / Sold To Dealer modal button. In Inventory is the
; default (downCount=0, leave it — this is the last field, no Tab
; needed); Sold To Dealer is one Down below it (downCount=1).
ModalSelect(downCount, label := "") {
	global DryRun, SleepMs, DryLog
	if (DryRun) {
		DryLog .= label "`n"
		return
	}
	if (downCount = 0)
		return
	Loop downCount {
		SendInput "{Down}"
		Sleep SleepMs
	}
	SendInput "{Space}"
	Sleep SleepMs
}

; ---- Clipboard parsing -------------------------------------------

; Parses the "KEY: value" lines written by the Copy to Clipboard
; button into a Map. Values may contain literal "\n" (backslash-n)
; standing in for embedded newlines in the *_PARAGRAPH fields —
; those get unescaped back into real newlines here.
ParseClipboard(clipText) {
	data := Map()
	for line in StrSplit(clipText, "`n", "`r") {
		pos := InStr(line, ": ")
		if (!pos)
			continue
		key := Trim(SubStr(line, 1, pos - 1))
		value := SubStr(line, pos + 2)
		value := StrReplace(value, "\n", "`n")
		data[key] := value
	}
	return data
}
