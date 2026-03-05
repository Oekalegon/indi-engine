# Design

INDI Engine will be a non-gui app that will be a layer between the INDI server and any clients. It allows for instance capturing sequences to continue when the client goes offline. The INDI engine is expected to be run on the same computer as the INDI server.

## Start/Stop INDI Server
One feature should be for the engine to be able to start and stop an INDI server. And add and remove drivers. This will allow clients to add new drivers and restart a server when stalled which sometimes happens when devices are connected or disconnected.
Adding drivers may involve compiling a driver from the 3rd party repository. Or is it possible to compile everything beforehand?

## State
The engine will keep track of device state. So if a property is updated in INDI the device that property belongs to is updated accordingly.
The client can request the information for a device and it will recieve all known properties for that device and their values. The client should also recieve all updates for the properties of the device when they are recieved by the engine. In this case however, only the updated property will be forwarded.

## Actions
Actions will be used to control the telescope rig(s). They will be written in python, the configuration in YAML.

Examples:
1. Park telescope, i.e. slew to park position and stop tracking
2. Go to object, i.e. slew the telescope to the position of the object, plate solve if there is a camera, slew until correct position, start tracking.
3. Sequencer, i.e. slew to position of object, refocus, start guiding, take a set number of images with specific configuration (including filter,e.g.), start next sequence item.

### Concurrency
An action should always check if devices are available. If not, either queue or warn client, depending on the settings put by the client.

### Using other actions
An action may use other actions and use the output for conditions. E.g. a weather action may evaluate the weather situation and output whether it is ok to start imaging, this may be used by the sequencer to start imaging.

### Availability
The engine should be able to provide the client with a list of actions available (and whether they are available at a specific time given the availability of the device)

## Communication
Communication should take place over sockets. The format will be json. Any configuration in YAML will be translated into JSON and then back again.

The client should be able to request information, e.g. the state of a device or devices, which actions are available.

## Image Frames
Image frames will be stored on the computer running the INDI server and engine, but the client may request the image to be send and deleted.
