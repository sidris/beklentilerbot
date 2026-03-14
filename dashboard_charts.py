import plotly.express as px


def revision_chart(df):
    if df.empty:
        return None

    fig = px.line(
        df.sort_values("updated_at"),
        x="updated_at",
        y="value",
        color="source_name",
        markers=True,
        hover_data=["entry_type", "forecast_type", "target_period"],
        title="Revizyon Grafiği",
    )
    return fig


def consensus_chart(df):
    if df.empty:
        return None

    fig = px.line(
        df.sort_values("target_period"),
        x="target_period",
        y="consensus",
        color="forecast_type",
        markers=True,
        title="Consensus",
    )
    return fig


def heatmap_chart(pivot_df):
    if pivot_df.empty:
        return None

    fig = px.imshow(
        pivot_df,
        aspect="auto",
        text_auto=True,
        title="Heatmap",
    )
    return fig
