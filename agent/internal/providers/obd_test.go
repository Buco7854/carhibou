package providers

import "testing"

func TestCANAndStandardOBDParsing(t *testing.T) {
	frame, err := ParseCANFrame("374 8 96 00 00 00 00 00 00 00", 12.5)
	if err != nil {
		t.Fatal(err)
	}
	if frame.CANID != 0x374 || frame.Data[0] != 0x96 {
		t.Fatalf("frame=%#v", frame)
	}
	if _, err := ParseCANFrame("374 8 01 02", 0); err == nil {
		t.Fatal("bad DLC accepted")
	}
	payload := ParseOBDResponse(1, 0x0C, []string{"7E8 04 41 0C 1A F8"})
	value, err := StandardPIDs[0x0C].Decode(payload)
	if err != nil || value != 1726 {
		t.Fatalf("rpm=%v err=%v", value, err)
	}
	if vin := ParseVIN([]string{"7E8 10 14 49 02 01 56 46 33", "7E8 21 31 58 58 58 58 58 58", "7E8 22 58 58 58 58 58 58 58"}); vin != "VF31XXXXXXXXXXXXX" {
		t.Fatalf("vin=%s", vin)
	}
	codes := ParseDTC([]string{"7E8 06 43 01 33 C1 23 00"})
	if len(codes) != 2 || codes[0] != "P0133" || codes[1] != "U0123" {
		t.Fatalf("codes=%#v", codes)
	}
}
