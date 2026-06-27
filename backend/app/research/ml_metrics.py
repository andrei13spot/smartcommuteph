# placeholder accuracy metrics for the predictive models, shown on the dashboard.
# real rmse/mae come from training on holdout test sets; these are stand-ins that
# match the current stub predictors.
def ml_metrics() -> dict:
    return {
        "models": [
            {
                "key": "lstm", "name": "LSTM · Ridership", "criterion": "T - ridership",
                "rmse": 0.072, "mae": 0.051, "detail": "24 mo hourly, 70/15/15 split",
                "status": "stub",
            },
            {
                "key": "rfr", "name": "RFR · Flood Risk", "criterion": "R - flood",
                "rmse": 0.094, "mae": 0.068, "detail": "MMDA reports + flood-prone map",
                "status": "stub",
            },
        ],
        "metric": "RMSE / MAE on holdout test set",
        "note": "placeholder values until the models are trained",
    }
