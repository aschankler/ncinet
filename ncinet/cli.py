"""
Main interface for ncinet.
"""

import os
import yaml

from . import CONFIG_DIR, WORK_DIR
from ncinet.config_meta import SessionConfig
from .options import parse_args


def standard_config(model_type, base_name):
    # type: (str, str) -> SessionConfig
    """Construct a default config from a file"""
    from ncinet.model_selection.hyper_parameters import make_config

    # Load the appropriate configuration file
    config_path = os.path.join(CONFIG_DIR, "{}_default.yml".format(model_type))
    with open(config_path, 'r') as config_file:
        config_dict = yaml.load(config_file)

    # Make config with the default parameters
    config = make_config(config_dict, basename=base_name)

    return config


def cli():
    options = parse_args()

    # Reset work dir if specified
    if options.work_dir:
        global WORK_DIR
        WORK_DIR = options.work_dir

    if options.mode == 'grid':
        from .model_selection.parameter_opt import grid_search
        with open(options.grid, 'r') as conf_file:
            params = yaml.load(conf_file)

        results = grid_search(**params)

        with open(options.output, 'w') as out_file:
            out_file.write(yaml.dump(results))

    elif options.mode == 'rand':
        from .model_selection.parameter_opt import random_search

        conf_path, n_iter = options.rand
        with open(conf_path, 'r') as conf_file:
            params = yaml.load(conf_file)

        results = random_search(params['fixed_params'], params['var_params'], int(n_iter))

        with open(options.output, 'w') as out_file:
            out_file.write(yaml.dump(results))

    elif options.mode == 'predict':
        import numpy as np
        from ncinet.config_meta import PredictIngestConfig
        from ncinet.predict import generate_predictions

        model_path, data_conf_path = options.predict

        # Build an ingest config based on input
        with open(data_conf_path) as data_conf_file:
            data_conf_dict = yaml.load(data_conf_file)

        data_conf = PredictIngestConfig(**data_conf_dict)

        # Run predictions
        results = generate_predictions(model_path, data_conf)

        # Write output
        np.savez(options.output, **results)

    else:
        # Make config
        if options.model == 'conf':
            from ncinet.model_selection.hyper_parameters import make_config, ae_fstring

            # Load the config file
            with open(options.conf, 'r') as conf_file:
                conf_dict = yaml.load(conf_file)
            if options.basename:
                config = make_config(conf_dict, basename=options.basename)
            else:
                config = make_config(conf_dict, fstring=ae_fstring)

        else:
            # Construct a standard basename if none provided
            autoencoder = options.model == 'encoder'
            base_name = ("" if autoencoder else "inf_") + options.model.lower()
            base_name = base_name if options.basename is None else options.basename

            # Make a default config using built-in files
            config = standard_config(options.model, base_name)

            if not autoencoder:
                config.train_config.encoder_dir = os.path.join(WORK_DIR, "encoder_train")

        if options.mode == 'train':
            from .train import main
            main(config)
        elif options.mode == 'eval':
            from .eval import main
            main(config)
        elif options.mode == 'xval':
            # Cross validate the conditions
            from ncinet.model_selection.parameter_opt import xval_condition
            _, result = xval_condition(config, 3)

            # Write out results
            with open(options.output, 'w') as out_file:
                yaml.dump(result, out_file)
        elif options.mode == 'serialize':
            from ncinet.predict import serialize_model

            if options.output:
                output_path = os.path.join(WORK_DIR, options.output)
            else:
                assert config.eval_config.eval_dir.endswith('_eval')
                basename = os.path.basename(config.eval_config.eval_dir[:-5])
                output_path = os.path.join(WORK_DIR, basename+'_serialized')

            serialize_model(config, output_path)
        else:
            raise ValueError
