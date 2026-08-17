# Data directory

The project uses score-level SATB data derived from the Bach chorales available through `music21` and optional external MusicXML/MXL pilot subsets.

Raw upstream corpora are not copied into this curated repository. Use the dataset-building scripts and corresponding configuration files after reviewing the original source terms.

The data interface is a fixed-grid tensor with voice order:

```text
soprano, alto, tenor, bass
```

The default grid is `quarterLength = 0.25`. MIDI numbers are internal symbolic pitch tokens; the intended research output is four-part MusicXML notation.
