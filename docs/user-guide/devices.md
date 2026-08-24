# Devices and enrollment

Create an enrollment for the intended vehicle and tracker name. The installer exchanges
the one-time token for a permanent random device credential, stores it mode `0600`, and
invalidates the token. Device credentials can only use device endpoints.

Revoke lost hardware immediately. Rotation returns the replacement credential once and
invalidates the old value. Re-enrollment uses a new enrollment token.
