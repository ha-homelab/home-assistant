# Inactive source configuration

`shadowed_input_number.yaml.disabled` was referenced by an earlier duplicate `input_number` key. Home Assistant used the later key, so these helpers were not loaded. The active `nightime` helper is in `config/integrations/input_number.yaml`.

Keep this archive outside all `!include_dir_*` paths. Enabling it is a behavior change requiring separate validation of its consumers.
