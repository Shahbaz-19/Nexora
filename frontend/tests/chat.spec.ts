import { expect, test, type Page } from "@playwright/test";

async function mockApi(page: Page, authenticated = true) {
  let signedIn = authenticated;
  let nextId = 1;
  let failQuery = false;
  let failDelete = false;
  type Message = {
    id: number;
    role: string;
    content: string;
    sources: object[];
    created_at: string;
  };
  const sessions: {
    id: number;
    title: string;
    created_at: string;
    updated_at: string;
    messages: Message[];
  }[] = [];
  await page.route("http://localhost:8000/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const now = new Date().toISOString();
    const reply = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        json: body,
        headers: {
          "Access-Control-Allow-Origin": "http://localhost:3000",
          "Access-Control-Allow-Credentials": "true",
        },
      });
    if (method === "OPTIONS") return reply({});
    if (path === "/auth/register") return reply({ id: 1 }, 201);
    if (path === "/auth/login") {
      if (request.postDataJSON().email === "invalid@example.com") {
        return reply({ detail: "Invalid email or password" }, 401);
      }
      signedIn = true;
      return reply({ access_token: "test-token" });
    }
    if (path === "/auth/refresh")
      return reply(
        signedIn ? { access_token: "test-token" } : {},
        signedIn ? 200 : 401,
      );
    if (path === "/auth/me")
      return reply({
        id: 1,
        full_name: "Engineering Tester",
        email: "test@example.com",
      });
    if (path === "/auth/logout") {
      signedIn = false;
      return reply({});
    }
    if (path === "/documents/upload")
      return reply(
        {
          id: nextId++,
          original_filename: "manual.txt",
          status: "READY",
          chunk_count: 1,
        },
        201,
      );
    if (path === "/chat/sessions" && method === "POST") {
      const session = {
        id: nextId++,
        title: "New chat",
        created_at: now,
        updated_at: now,
        messages: [],
      };
      sessions.unshift(session);
      return reply(session, 201);
    }
    if (path === "/chat/sessions") return reply(sessions);
    if (path === "/chat/query" || path === "/chat/query/stream") {
      if (failQuery)
        return reply(
          { detail: "Internal exception should never be displayed" },
          500,
        );
      const body = request.postDataJSON();
      const session = sessions.find((item) => item.id === body.session_id)!;
      if (!session.messages.length) session.title = body.query;
      const user = {
        id: nextId++,
        role: "USER",
        content: body.query,
        sources: [],
        created_at: now,
      };
      const assistant = {
        id: nextId++,
        role: "ASSISTANT",
        content:
          "## Engineering answer\n\n**Direct link to shareholder wealth** and *evidence*.\n\n1. First finding\n2. Second finding\n\n- A useful detail\n\nUse `NPV`.\n\n```python\nprint(18)\n```\n\n<script>alert('unsafe')</script>",
        sources: [
          {
            document_id: 1,
            filename: "Investment Appraisal Theory Questions.pdf",
            page_number: 2,
            chunk_index: 1,
            similarity_score: 0.8,
          },
        ],
        created_at: now,
      };
      session.messages.push(user, assistant);
      session.updated_at = now;
      const payload = {
        session_id: session.id,
        session,
        user_message: user,
        assistant_message: assistant,
        answer: assistant.content,
        sources: assistant.sources,
      };
      if (path === "/chat/query/stream") {
        const words = assistant.content.match(/\S+\s*/g) ?? [];
        const body = [
          `event: metadata\ndata: ${JSON.stringify({ session_id: session.id, session, user_message: user })}\n\n`,
          ...words.map((content) => `event: delta\ndata: ${JSON.stringify({ content })}\n\n`),
          `event: complete\ndata: ${JSON.stringify(payload)}\n\n`,
        ].join("");
        return route.fulfill({
          status: 200,
          body,
          contentType: "text/event-stream",
          headers: {
            "Access-Control-Allow-Origin": "http://localhost:3000",
            "Access-Control-Allow-Credentials": "true",
          },
        });
      }
      return reply(payload);
    }
    const id = Number(path.split("/").at(-1));
    const index = sessions.findIndex((item) => item.id === id);
    if (index >= 0 && method === "DELETE") {
      if (failDelete) return reply({}, 500);
      sessions.splice(index, 1);
      return route.fulfill({ status: 204 });
    }
    if (index >= 0) return reply(sessions[index]);
    return reply({}, 404);
  });
  return {
    failSend: (value: boolean) => {
      failQuery = value;
    },
    failDelete: (value: boolean) => {
      failDelete = value;
    },
  };
}

test("history, uploads, Markdown, refresh, switching, errors, deletion, and sign out", async ({
  page,
}) => {
  const api = await mockApi(page);
  await page.goto("/dashboard");
  await expect(page.locator('link[rel="icon"]')).toHaveAttribute("href", /icon/);
  await expect(page.locator(".brand .nexora-logo")).toBeVisible();
  await expect(page.getByText("Document intelligence", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Engineering knowledge, grounded in your documents", { exact: true })).toHaveCount(0);
  await expect(page.getByText("What would you like to know?")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Documents", exact: true }),
  ).toHaveCount(0);
  await page
    .locator('input[type="file"]')
    .setInputFiles({
      name: "manual.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Pressure is 18 bar."),
    });
  await expect(page.getByText("Ready in your knowledge base")).toBeVisible();
  await page
    .getByRole("button", { name: "Dismiss manual.txt notification" })
    .click();
  await page
    .getByRole("textbox", { name: "Your question" })
    .fill("Why is NPV useful?");
  await page.getByRole("textbox", { name: "Your question" }).press("Enter");
  await expect(page.locator(".markdown strong")).toHaveText(
    "Direct link to shareholder wealth",
  );
  await expect(page.locator(".markdown ol li")).toHaveCount(2);
  await expect(page.locator(".markdown pre code")).toContainText("print(18)");
  await expect(page.locator(".markdown script")).toHaveCount(0);
  await expect(page.getByText("Page 2 • Chunk 2")).toBeVisible();
  await page
    .getByRole("textbox", { name: "Your question" })
    .fill("Explain further");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.locator(".assistant-message")).toHaveCount(2);
  await page.reload();
  await page
    .getByRole("button", { name: "Why is NPV useful?", exact: true })
    .click();
  await expect(page.locator(".assistant-message")).toHaveCount(2);
  await page.getByRole("button", { name: "New Chat", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Your question" }),
  ).toHaveValue("");
  await page
    .getByRole("textbox", { name: "Your question" })
    .fill("Second conversation");
  await page.getByRole("textbox", { name: "Your question" }).press("Enter");
  await expect(page.locator(".assistant-message")).toHaveCount(1);
  api.failSend(true);
  await page
    .getByRole("textbox", { name: "Your question" })
    .fill("Retry this question");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.locator(".chat-error")).toContainText("Could not send");
  await expect(
    page.getByRole("textbox", { name: "Your question" }),
  ).toHaveValue("Retry this question");
  api.failSend(false);
  await page
    .getByRole("button", { name: "Why is NPV useful?", exact: true })
    .click();
  await expect(page.locator(".assistant-message")).toHaveCount(2);
  api.failDelete(true);
  await page.getByLabel("Actions for Why is NPV useful?").click();
  await page.getByRole("button", { name: "Delete conversation" }).click();
  await expect(page.locator(".chat-error")).toContainText("Could not delete");
  api.failDelete(false);
  await page.getByLabel("Actions for Why is NPV useful?").click();
  await page.getByRole("button", { name: "Delete conversation" }).click();
  await expect(page.getByText("What would you like to know?")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Why is NPV useful?", exact: true }),
  ).toHaveCount(0);
  await page.screenshot({ path: "test-results/dashboard-desktop.png" });
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/login/);
});

test("mobile drawer, composer, and layout", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto("/dashboard");
  await expect(
    page.getByRole("textbox", { name: "Your question" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(
    page.getByRole("button", { name: "New Chat", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "New Chat", exact: true }),
  ).not.toBeVisible();
  await page
    .getByRole("textbox", { name: "Your question" })
    .fill("Mobile question");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.locator(".assistant-message")).toHaveCount(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  const composer = await page.locator(".composer").boundingBox();
  expect(composer!.y + composer!.height).toBeLessThanOrEqual(844);
  await page.screenshot({ path: "test-results/dashboard-mobile.png" });
});

test("signup and login retain their existing flow", async ({ page }) => {
  await mockApi(page, false);
  await page.goto("/login");
  await expect(page.locator(".auth-card")).toBeVisible();
  await expect(page.locator(".auth-card .nexora-logo")).toBeVisible();
  await expect(page.getByText("Nexora", { exact: true })).toBeVisible();
  await expect(page.getByText("Forgot password?", { exact: true })).toHaveCount(0);

  await page.getByLabel("Email", { exact: true }).fill("invalid@example.com");
  await page.getByLabel("Password", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
  await expect(page.locator(".auth-error")).toHaveText("Invalid email or password.");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");
  await page.getByRole("link", { name: "Create account" }).click();
  await expect(page).toHaveURL(/signup/);

  await page.goto("/signup");
  await page
    .getByLabel("Full name", { exact: true })
    .fill("Engineering Tester");
  await page.getByLabel("Email", { exact: true }).fill("test@example.com");
  await page.getByLabel("Password", { exact: true }).fill("Example-123!");
  await page
    .getByLabel("Confirm password", { exact: true })
    .fill("different-password");
  await page
    .getByRole("button", { name: "Create Account", exact: true })
    .click();
  await expect(page.locator(".auth-error")).toHaveText("Passwords do not match.");
  await page
    .getByLabel("Confirm password", { exact: true })
    .fill("Example-123!");
  await page
    .getByRole("button", { name: "Create Account", exact: true })
    .click();
  await expect(page).toHaveURL(/login/);
  await page.getByLabel("Email", { exact: true }).fill("test@example.com");
  await page.getByLabel("Password", { exact: true }).fill("Example-123!");
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
  await expect(page).toHaveURL(/dashboard/);
});

test("auth cards remain usable on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockApi(page, false);
  await page.goto("/login");
  await expect(page.locator(".auth-card")).toBeVisible();
  await expect(page.locator(".auth-floating-logo")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/auth-login-mobile.png", fullPage: true });
  await page.getByRole("link", { name: "Create account" }).click();
  await expect(page).toHaveURL(/signup/);
  await expect(page.locator(".auth-card")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/auth-signup-mobile.png", fullPage: true });
});

test("upload failure, empty queries, Shift+Enter, and expired access retry", async ({ page }) => {
  await mockApi(page);
  let firstListRequest = true;
  await page.route("http://localhost:8000/chat/sessions", route => {
    if (firstListRequest && route.request().method() === "GET") {
      firstListRequest = false;
      return route.fulfill({ status: 401, json: {} });
    }
    return route.fallback();
  });
  await page.route("http://localhost:8000/documents/upload", route => route.fulfill({ status: 500, json: { detail: "private error" } }));
  await page.goto("/dashboard");
  await expect(page.getByText("A fresh start")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send question" })).toBeDisabled();
  await page.locator('input[type="file"]').setInputFiles({ name: "manual.txt", mimeType: "text/plain", buffer: Buffer.from("Test document") });
  await expect(page.locator(".chat-error")).toContainText("Could not process this document");
  await expect(page.getByText("private error")).toHaveCount(0);
  await page.getByRole("textbox", { name: "Your question" }).fill("First line");
  await page.getByRole("textbox", { name: "Your question" }).press("Shift+Enter");
  await page.getByRole("textbox", { name: "Your question" }).pressSequentially("Second line");
  await expect(page.getByRole("textbox", { name: "Your question" })).toHaveValue("First line\nSecond line");
  await expect(page.locator(".user-message")).toHaveCount(0);
  await page.getByRole("textbox", { name: "Your question" }).press("Enter");
  await expect(page.locator(".assistant-message")).toHaveCount(1);
  await page.getByRole("button", { name: "New Chat", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Your question" })).toBeFocused();
});
