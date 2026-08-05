# Rendering model

The pure renderer builds an in-memory `ScreenBuffer` of immutable-style cells.
The first frame (and every resize) is serialized as a full repaint. Later frames
emit cursor moves only for changed cells. Drawing is clipped at every operation,
and labels prefer right, left, below, then above without moving aircraft markers.
Projection uses a north-up ellipse: sine controls horizontal displacement and
cosine controls vertical displacement, compensating for non-square terminal cells.
