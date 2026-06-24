# Data

Default data source: built-in `music21` Bach chorales.

No external download is required for the smoke experiment. Optional external MusicXML input can be supplied through `data.external_xml_dir` in a config file.

Processed datasets are written to `data/processed/*.npz` and contain:

- `tokens`: padded SATB token arrays of shape `(N, T, 4)`
- `lengths`: unpadded sequence lengths
- `splits`: deterministic train/val/test labels
- `names`: source names
- tokenizer metadata such as grid size and MIDI range

Raw external MusicXML files, if used, can be placed in `data/raw/`.
