import pytest
from notte_browser.session import NotteSession
from notte_core.actions import (
    ClickAction,
    FillAction,
    GotoAction,
    ScrapeAction,
    ScrollDownAction,
    ScrollUpAction,
    WaitAction,
)

# .set_user_agent(
#             "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
#         )


@pytest.mark.asyncio
async def test_huggingface_model_search():
    async with NotteSession(enable_perception=False) as page:
        _ = await page.astep(GotoAction(url="https://huggingface.co/models"))
        _ = await page.astep(FillAction(id="I1", value="sentiment analysis"))
        _ = await page.astep(WaitAction(time_ms=2000))
        _ = await page.astep(ClickAction(id="L17"))
        _ = await page.astep(ClickAction(id="L12"))
        _ = await page.astep(ScrollDownAction(amount=None))
        _ = await page.astep(ScrollDownAction(amount=None))
        _ = await page.astep(ScrollDownAction(amount=None))
        _ = await page.astep(ScrollUpAction(amount=500))


@pytest.mark.asyncio
async def test_google_search():
    async with NotteSession(enable_perception=False) as page:
        _ = await page.astep(GotoAction(url="https://www.google.com"))
        if not page.snapshot.dom_node.find("I1"):
            # agree to cookies if menu is present
            _ = await page.astep(ClickAction(id="B3"))
        _ = await page.astep(FillAction(id="I1", value="test_query"))
        _ = await page.astep(ClickAction(id="O2"))


@pytest.mark.skip(reason="This test is not working on the CI for some reason")
@pytest.mark.asyncio
async def test_reddit_fill_search_and_click():
    async with NotteSession(enable_perception=False) as page:
        _ = await page.astep(GotoAction(url="https://www.reddit.com"))
        _ = await page.astep(WaitAction(time_ms=3000))
        _ = await page.astep(FillAction(id="I1", value="browser-use", press_enter=True))
        _ = await page.astep(ClickAction(id="B1"))
        _ = await page.astep(ClickAction(id="B4"))
        _ = await page.astep(WaitAction(time_ms=5000))
        _ = await page.astep(ClickAction(id="L4"))


@pytest.mark.skip(reason="This test is not working on the CI for some reason")
@pytest.mark.asyncio
async def test_bbc_click_cookie_policy_link():
    async with NotteSession(enable_perception=False) as page:
        obs = await page.astep(GotoAction(url="https://www.bbc.com"))
        assert len(obs.metadata.tabs) == 1
        obs = await page.astep(ClickAction(id="L1"))
        assert len(obs.metadata.tabs) == 2
        obs = await page.astep(ScrapeAction())
        assert obs.data is not None
        assert obs.data.markdown is not None
        assert "BBC" in obs.data.markdown
        assert "cookies" in obs.data.markdown


@pytest.mark.asyncio
async def test_wikipedia_search():
    async with NotteSession(enable_perception=False) as page:
        _ = await page.astep(GotoAction(url="https://www.wikipedia.org/"))
        _ = await page.astep(FillAction(id="I1", value="Nadal"))
        _ = await page.astep(ClickAction(id="L11"))
        _ = await page.astep(ScrapeAction())


@pytest.mark.asyncio
async def test_allrecipes_search():
    async with NotteSession(enable_perception=False) as page:
        _ = await page.astep(GotoAction(url="https://www.allrecipes.com"))
        consent_cookie = page.snapshot.dom_node.find("B3")
        if consent_cookie and "Consent" in consent_cookie.text:
            _ = await page.astep(ClickAction(id="B3"))
        _ = await page.astep(FillAction(id="I1", value="chicken breast and quinoa"))
        _ = await page.astep(ClickAction(id="B1"))
        _ = await page.astep(ScrapeAction())
        _ = await page.astep(
            GotoAction(url="https://www.allrecipes.com/recipe/215076/chicken-with-quinoa-and-veggies/")
        )
        _ = await page.astep(ScrollDownAction(amount=500))
