# Network

The INDI engine can be one node in a network of INDI engines. Some will be connected to an INDI server on the same computer. Others will just be connected to other INDI engines in the same network. A client is a leaf node and should connect to one or more engines.

INDI engines will have different functionalities. 

- Connect to an INDI server and forward messages. This engine may also have scripts to run sequences of INDI messages for instance to slew a telescope, or to capture a frame, or to keep a schedule for capturing frames of different objects.
- Peform calculations, e.g. calibrating frames, or plate solving
- Archiving images

INDI engines may of course combine these functionalities.

## Subscriptions

Each client and engine should subscribe to messages from specific other engines (and maybe specific devices if that engine is connected to a INDI server).
Each engine should keep a list of subscribed engines and clients so that it knows where to send which messages to.
Engines can not subscribe to clients, clients can subscribe to engines. 
If subscribing to an engine without specifying a device, all messages from that engine should be forwarded.
No direct connection needs to exist between an engine and an engine it is subscribed to. The connection can be over several links.

## Discoverable

Use bonjour to make each engine discoverable. Each engine should publish a list of all the other engines it knows about (not only the ones it is subscribed to). 
When an engine comes online it should broadcast its availability to the network. And when other engines notice that an engine goes offline, that should also be broadcast. Of course, if an engine is gracefully shutdown, it should broadcast this itself, but if it e.g. crashes, the offline status should be broadcast by other engines that were connected to that engine.

## Capabilities

Engines should be able to send a message describing its capabilities when requested. 
If the engine is connected to an INDI server, the connected devices and scripts it can execute are its capabilities. If the engine can perform plate solving, that should be anounced as a capability.
A set of default capabilities should be defined (in an enum?).

## Provenance

Messages should keep provenance, i.e. the chain of engines it goes through. For instance when we have an INDI message from an INDI server with ID X, which is connected to engine A, that is connected to engine B, and client C is connected to engine B. That message should show provenance X -> A -> B when it arrives at C. 
When forwarding messages engines should check if it is itself not yet in the provenance, this to prevent circularity.

## Configuration

The configuration of the engine should probably be defined in a configuration (YAML) file.
This should include the capabilities it can perform (e.g. we should be able to define which scripts can be executed by the engine (not necessarily all that are available)), the identifier and name for the engine (default name should be the computer name), whether it is connected to an INDI server (and its id and name), and the subscriptions it automatically subscribes to.
The names and subscriptions should be editable by clients via messages.

