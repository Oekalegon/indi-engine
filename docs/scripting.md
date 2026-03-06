# Action Scripting

INDI Engine is mostly a action scripting engine. It should allow users to run scripts that generate INDI commands to the INDI server. For instance, scripts can exist to take dark frames, or to slew the telescope to a specific object and start tracking. Many scripts will be predefined in the INDI Engine, but a user may add new scripts. These scripts may be uploaded to the server by the client.

Scripts can only execute INDI commands and get information from INDI. Some other functionality should be available to the script, i.e. time information and probably astronomical information from the astropy library (and associated libraries) and fitsio.