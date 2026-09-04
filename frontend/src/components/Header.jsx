import { SparkIcon } from "./icons";

function Header() {
  return (
    <header className="app-header">
      <div className="app-header__inner">
        <div className="brand">
          <div className="brand__mark">
            <SparkIcon width={22} height={22} />
          </div>
          <div className="brand__text">
            <h1>Code2Video</h1>
            <p>Turn source code into narrated algorithm animations</p>
          </div>
        </div>

        <a
          className="brand__badge"
          href="https://www.manim.community/"
          target="_blank"
          rel="noreferrer"
        >
          Powered by Manim + AI
        </a>
      </div>
    </header>
  );
}

export default Header;
